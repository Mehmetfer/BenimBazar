"""Crypto risk bridge — reuses RiskEngine pause/limits; fractional sizing for crypto."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config.models import CapitalMode, IndicatorSet, OpportunityMetrics, RiskLevel, SignalAction, TradePlan
from config.settings import Settings, settings as default_settings
from crypto.trade_plan_crypto import crypto_size_from_risk
from risk.engine import ENTRY_ACTIONS, EXIT_ACTIONS, RiskDecision, RiskEngine, RiskVerdict


@dataclass
class CryptoRiskResult:
    allowed: bool
    verdict: str
    reason: str
    quantity: float
    stop_price: float | None
    target_price: float | None
    risk_level: str
    risk_reward: float | None
    size_mult: float
    market_type: str = "CRYPTO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_crypto_entry(
    risk: RiskEngine,
    *,
    symbol: str,
    price: float,
    ind: IndicatorSet,
    action: SignalAction,
    plan: TradePlan | None,
    spread_pct: float,
    opportunity: OpportunityMetrics | None,
    size_mult: float = 1.0,
    max_spread_pct: float | None = None,
    max_exposure_pct: float = 15.0,
    atr_cap_pct: float = 8.0,
    cfg: Settings | None = None,
) -> CryptoRiskResult:
    """Apply shared risk architecture with crypto-specific size + volatility caps."""
    cfg = cfg or risk.cfg or default_settings
    max_spread = max_spread_pct if max_spread_pct is not None else max(cfg.max_spread_pct, 1.5)

    risk.refresh_pause_state()
    if cfg.kill_switch or risk.capital_mode == CapitalMode.KILL_SWITCH:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "KILL_SWITCH", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)
    if cfg.is_live:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "LIVE_DISABLED_PAPER_ONLY", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)
    if risk.paused:
        return CryptoRiskResult(False, RiskVerdict.WAIT.value, risk.pause_reason or "paused", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult, )
    if risk.ledger.daily_loss_pct() <= -cfg.daily_max_loss_pct:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "daily_loss_limit", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)
    if risk.ledger.drawdown_pct() >= cfg.max_drawdown_pct:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "max_drawdown", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)
    if spread_pct > max_spread:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "excessive_spread", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)

    if action not in ENTRY_ACTIONS:
        return CryptoRiskResult(False, RiskVerdict.WAIT.value, "not_an_entry", 0, None, None, RiskLevel.LOW.value, None, size_mult)

    atr_pct = (ind.atr14 / price * 100) if price else 99.0
    if atr_pct > atr_cap_pct:
        return CryptoRiskResult(False, RiskVerdict.WAIT.value, "crypto_volatility_cap", 0, None, None, RiskLevel.HIGH.value, None, size_mult)

    if opportunity is not None and opportunity.expected_value <= cfg.min_expected_value:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "negative_or_zero_ev", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)

    if plan is None:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "no_trade_plan", 0, None, None, RiskLevel.BLOCKED.value, None, size_mult)

    stop, t1, rr = plan.stop, plan.target1, plan.risk_reward
    if stop <= 0 or stop >= price:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "invalid_stop", 0, stop, t1, RiskLevel.BLOCKED.value, rr, size_mult)
    if rr < cfg.min_risk_reward:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "rr_below_minimum", 0, stop, t1, RiskLevel.BLOCKED.value, rr, size_mult)

    if risk.ledger.open_position_count() >= cfg.max_open_positions:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "max_open_positions", 0, stop, t1, RiskLevel.BLOCKED.value, rr, size_mult)

    equity = risk.ledger.equity()
    cash = risk.ledger.cash
    qty, _, _ = crypto_size_from_risk(
        equity=equity,
        entry=price,
        stop=stop,
        size_mult=size_mult,
        max_exposure_pct=max_exposure_pct,
        cash=cash,
        cfg=cfg,
    )
    if qty <= 0:
        return CryptoRiskResult(False, RiskVerdict.WAIT.value, "qty_zero", 0, stop, t1, RiskLevel.HIGH.value, rr, size_mult)

    level = RiskLevel.LOW if abs(price - stop) / price < 0.03 else RiskLevel.MEDIUM
    if atr_pct > 4:
        level = RiskLevel.HIGH
    verdict = RiskVerdict.REDUCE if size_mult < 0.99 else RiskVerdict.APPROVE
    return CryptoRiskResult(
        True,
        verdict.value,
        "ok" if verdict == RiskVerdict.APPROVE else "ok_reduced",
        qty,
        round(stop, 6),
        round(t1, 6),
        level.value,
        rr,
        size_mult,
    )


def evaluate_crypto_exit(risk: RiskEngine, action: SignalAction) -> CryptoRiskResult:
    if action not in EXIT_ACTIONS:
        return CryptoRiskResult(False, RiskVerdict.WAIT.value, "not_an_exit", 0, None, None, RiskLevel.LOW.value, None, 1.0)
    if risk.cfg.kill_switch:
        return CryptoRiskResult(False, RiskVerdict.REJECT.value, "KILL_SWITCH", 0, None, None, RiskLevel.BLOCKED.value, None, 1.0)
    return CryptoRiskResult(True, RiskVerdict.APPROVE.value, "ok", 0, None, None, RiskLevel.LOW.value, None, 1.0)
