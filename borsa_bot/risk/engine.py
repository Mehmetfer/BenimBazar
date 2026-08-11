from __future__ import annotations

from dataclasses import dataclass

from config.models import (
    CapitalMode,
    IndicatorSet,
    OpportunityMetrics,
    RiskLevel,
    SignalAction,
    TradePlan,
)
from config.settings import Settings, settings as default_settings
from portfolio.ledger import PortfolioLedger
from profit.protection import refuse_add_to_loser


ENTRY_ACTIONS = {SignalAction.AL, SignalAction.BUY, SignalAction.STRONG_BUY}
EXIT_ACTIONS = {SignalAction.SAT, SignalAction.SELL, SignalAction.STRONG_SELL}


@dataclass
class RiskDecision:
    allowed: bool
    risk: RiskLevel
    quantity: float
    stop_price: float | None
    target_price: float | None
    reason: str
    targets: tuple[float, float, float] | None = None
    risk_reward: float | None = None
    paused: bool = False
    size_mult: float = 1.0


class RiskEngine:
    """Highest-authority gate. NO TRADE / negative EV / capital modes override signals."""

    def __init__(self, ledger: PortfolioLedger, cfg: Settings | None = None) -> None:
        self.ledger = ledger
        self.cfg = cfg or default_settings
        self.paused = False
        self.pause_reason = ""
        self.capital_mode = CapitalMode.NORMAL

    def refresh_pause_state(self) -> None:
        losses = self.ledger.consecutive_losses()
        if losses >= self.cfg.consecutive_loss_pause:
            self.paused = True
            self.pause_reason = f"consecutive_losses>={self.cfg.consecutive_loss_pause}"
        dd = self.ledger.drawdown_pct()
        if dd >= self.cfg.max_drawdown_pct:
            self.paused = True
            self.pause_reason = "max_drawdown"
        if self.ledger.weekly_loss_pct() <= -self.cfg.weekly_max_loss_pct:
            self.paused = True
            self.pause_reason = "weekly_loss_limit"

    def evaluate_entry(
        self,
        *,
        symbol: str,
        sector: str,
        price: float,
        ind: IndicatorSet,
        action: SignalAction,
        plan: TradePlan | None = None,
        spread_pct: float = 0.0,
        correlated_sector_risk: float = 0.0,
        opportunity: OpportunityMetrics | None = None,
        capital_mode: CapitalMode | None = None,
        size_mult: float = 1.0,
    ) -> RiskDecision:
        self.refresh_pause_state()
        mode = capital_mode or self.capital_mode
        if self.cfg.kill_switch or mode == CapitalMode.KILL_SWITCH:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "KILL_SWITCH")
        if self.cfg.is_live:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "LIVE_DISABLED")
        if mode == CapitalMode.CAPITAL_PROTECTION:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "capital_protection_mode")
        if self.paused:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, self.pause_reason, paused=True)
        if self.ledger.daily_loss_pct() <= -self.cfg.daily_max_loss_pct:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "daily_loss_limit")
        if spread_pct > self.cfg.max_spread_pct:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "excessive_spread")
        if action not in ENTRY_ACTIONS:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "not_an_entry")

        # No DCA / add to loser by default
        existing = self.ledger.get_position(symbol)
        if existing and refuse_add_to_loser(avg_cost=existing.avg_cost, price=price):
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "no_add_to_losing_position")

        if opportunity is not None and opportunity.expected_value <= self.cfg.min_expected_value:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "negative_or_zero_ev")

        if plan is None:
            stop = price - ind.atr14 * self.cfg.atr_stop_mult
            risk_ps = price - stop
            if risk_ps <= 0:
                return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "stop_undefined")
            t1 = price + risk_ps * self.cfg.min_risk_reward
            t2 = price + risk_ps * self.cfg.preferred_risk_reward
            t3 = price + risk_ps * 3.0
            rr = self.cfg.min_risk_reward
        else:
            stop, t1, t2, t3, rr = plan.stop, plan.target1, plan.target2, plan.target3, plan.risk_reward
            risk_ps = price - stop

        if stop <= 0 or stop >= price:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "invalid_atr_stop")
        if rr < self.cfg.min_risk_reward:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, t1, "rr_below_minimum", (t1, t2, t3), rr)

        equity = self.ledger.equity()
        risk_budget = equity * (self.cfg.max_position_risk_pct / 100)
        atr_pct = ind.atr14 / price * 100 if price else 0
        if atr_pct > 3.5:
            risk_budget *= 0.6
        if self.ledger.consecutive_losses() >= self.cfg.consecutive_loss_reduce:
            risk_budget *= 0.5
        risk_budget *= max(0.0, min(1.0, size_mult))
        if risk_budget <= 0:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, t1, "size_mult_zero", (t1, t2, t3), rr, size_mult=size_mult)

        qty = int(risk_budget / risk_ps) if risk_ps > 0 else 0
        if qty <= 0:
            return RiskDecision(False, RiskLevel.HIGH, 0, stop, t1, "qty_zero", (t1, t2, t3), rr, size_mult=size_mult)
        if qty * price > self.ledger.cash:
            qty = int(self.ledger.cash / price)
        if qty <= 0:
            return RiskDecision(False, RiskLevel.HIGH, 0, stop, t1, "insufficient_cash", (t1, t2, t3), rr, size_mult=size_mult)
        if self.ledger.open_position_count() >= self.cfg.max_open_positions:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, t1, "max_open_positions", (t1, t2, t3), rr, size_mult=size_mult)
        if self.ledger.sector_position_count(sector) >= self.cfg.max_sector_positions:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, t1, "max_sector_positions", (t1, t2, t3), rr, size_mult=size_mult)
        if correlated_sector_risk > self.cfg.max_portfolio_risk_pct:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, t1, "sector_risk_budget", (t1, t2, t3), rr, size_mult=size_mult)

        risk_level = RiskLevel.LOW if (risk_ps / price) < 0.03 else RiskLevel.MEDIUM
        if atr_pct > 4:
            risk_level = RiskLevel.HIGH
        return RiskDecision(
            True,
            risk_level,
            float(qty),
            round(stop, 2),
            round(t1, 2),
            "ok",
            (round(t1, 2), round(t2, 2), round(t3, 2)),
            rr,
            size_mult=size_mult,
        )

    def evaluate_exit(self, symbol: str, action: SignalAction) -> RiskDecision:
        if self.cfg.kill_switch:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "KILL_SWITCH")
        pos = self.ledger.get_position(symbol)
        if not pos:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "no_position")
        if action not in EXIT_ACTIONS:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "not_an_exit")
        return RiskDecision(True, RiskLevel.LOW, pos.quantity, None, None, "ok")

    def preflight_live(self, *, data_fresh: bool, api_ok: bool, market_open: bool) -> tuple[bool, list[str]]:
        checks = {
            "api_connection": api_ok,
            "data_validation": data_fresh,
            "portfolio_validation": self.ledger.equity() > 0,
            "open_orders_check": True,
            "open_positions_check": True,
            "risk_limits": not self.cfg.kill_switch and not self.paused,
            "market_hours": market_open,
            "kill_switch_off": not self.cfg.kill_switch,
            "daily_loss_ok": self.ledger.daily_loss_pct() > -self.cfg.daily_max_loss_pct,
            "manual_approval_mode": self.cfg.require_manual_approval or not self.cfg.is_live,
            "paper_first": not self.cfg.is_live,
        }
        failed = [k for k, v in checks.items() if not v]
        return len(failed) == 0, failed
