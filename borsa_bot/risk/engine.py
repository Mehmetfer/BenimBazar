from __future__ import annotations

from dataclasses import dataclass

from config.models import IndicatorSet, OrderRequest, RiskLevel, SignalAction
from config.settings import Settings, settings as default_settings
from portfolio.ledger import PortfolioLedger


@dataclass
class RiskDecision:
    allowed: bool
    risk: RiskLevel
    quantity: float
    stop_price: float | None
    target_price: float | None
    reason: str


class RiskEngine:
    def __init__(self, ledger: PortfolioLedger, cfg: Settings | None = None) -> None:
        self.ledger = ledger
        self.cfg = cfg or default_settings

    def evaluate_entry(
        self,
        *,
        symbol: str,
        sector: str,
        price: float,
        ind: IndicatorSet,
        action: SignalAction,
    ) -> RiskDecision:
        if self.cfg.kill_switch:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "KILL_SWITCH")
        if self.cfg.is_live:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "LIVE_DISABLED")
        if self.ledger.daily_loss_pct() <= -self.cfg.daily_max_loss_pct:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "daily_loss_limit")
        if action != SignalAction.AL:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "not_an_entry")

        stop = price - ind.atr14 * self.cfg.atr_stop_mult
        target = price + ind.atr14 * self.cfg.atr_take_mult
        if stop <= 0 or stop >= price:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "invalid_atr_stop")

        equity = self.ledger.equity()
        risk_budget = equity * (self.cfg.max_position_risk_pct / 100)
        per_share_risk = price - stop
        qty = int(risk_budget / per_share_risk) if per_share_risk > 0 else 0
        cost = qty * price
        if qty <= 0:
            return RiskDecision(False, RiskLevel.HIGH, 0, stop, target, "qty_zero")
        if cost > self.ledger.cash:
            qty = int(self.ledger.cash / price)
        if qty <= 0:
            return RiskDecision(False, RiskLevel.HIGH, 0, stop, target, "insufficient_cash")
        if self.ledger.open_position_count() >= self.cfg.max_open_positions:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, target, "max_open_positions")
        if self.ledger.sector_position_count(sector) >= self.cfg.max_sector_positions:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, stop, target, "max_sector_positions")
        if self.ledger.consecutive_losses() >= 3:
            qty = max(1, qty // 2)

        risk_level = RiskLevel.LOW if (per_share_risk / price) < 0.03 else RiskLevel.MEDIUM
        return RiskDecision(True, risk_level, float(qty), round(stop, 2), round(target, 2), "ok")

    def evaluate_exit(self, symbol: str, action: SignalAction) -> RiskDecision:
        if self.cfg.kill_switch:
            return RiskDecision(False, RiskLevel.BLOCKED, 0, None, None, "KILL_SWITCH")
        pos = self.ledger.get_position(symbol)
        if not pos:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "no_position")
        if action != SignalAction.SAT:
            return RiskDecision(False, RiskLevel.LOW, 0, None, None, "not_an_exit")
        return RiskDecision(True, RiskLevel.LOW, pos.quantity, None, None, "ok")

    def preflight_live(self, *, data_fresh: bool, api_ok: bool, market_open: bool) -> tuple[bool, list[str]]:
        """Mandatory LIVE gates — all must pass before any live order path."""
        checks = {
            "api_connection": api_ok,
            "data_validation": data_fresh,
            "portfolio_validation": self.ledger.equity() > 0,
            "open_orders_check": True,  # paper: always clear
            "open_positions_check": True,
            "risk_limits": not self.cfg.kill_switch,
            "market_hours": market_open,
            "kill_switch_off": not self.cfg.kill_switch,
            "daily_loss_ok": self.ledger.daily_loss_pct() > -self.cfg.daily_max_loss_pct,
        }
        failed = [k for k, v in checks.items() if not v]
        return len(failed) == 0, failed
