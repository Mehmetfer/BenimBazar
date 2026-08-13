"""GÖREV 14 — Independent risk gate in front of the decision engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from decision.market_state import MarketState
from decision.signals import CompositeSignal, SignalDirection


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


@dataclass
class RiskLimits:
    max_position_size: float = 1000.0
    max_exposure_pct: float = 80.0  # matches MarketState exposure_pct scale (0–100)
    max_daily_loss: float = 500.0
    max_drawdown_pct: float = 15.0  # percent
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    confidence_threshold: float = 0.45
    consecutive_loss_limit: int = 3
    volatility_scale: float = 1.0
    liquidity_min_score: float = 35.0  # MarketState liquidity score 0–100


@dataclass
class RiskGateResult:
    verdict: RiskVerdict
    approved_size: float
    reasons: List[str] = field(default_factory=list)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "approved_size": self.approved_size,
            "reasons": list(self.reasons),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_state": dict(self.risk_state),
        }


def evaluate_risk(
    state: MarketState,
    signal: CompositeSignal,
    *,
    requested_size: float,
    limits: Optional[RiskLimits] = None,
    consecutive_losses: int = 0,
    daily_pnl: float = 0.0,
    peak_equity: float = 10000.0,
    current_equity: float = 10000.0,
) -> RiskGateResult:
    """SIGNAL → RISK CHECK → APPROVED / REDUCED / REJECTED."""
    limits = limits or RiskLimits()
    reasons: List[str] = []
    size = max(0.0, float(requested_size))

    price = float(state.price.last.value) if state.price.last.known() else None
    capital = float(state.portfolio.cash.value) if state.portfolio.cash.known() else None
    exposure = float(state.portfolio.exposure_pct.value) if state.portfolio.exposure_pct.known() else 0.0

    # Prefer portfolio consecutive losses when known
    if state.portfolio.consecutive_losses.known():
        consecutive_losses = max(consecutive_losses, int(float(state.portfolio.consecutive_losses.value)))
    if state.portfolio.drawdown_pct.known():
        portfolio_dd = float(state.portfolio.drawdown_pct.value)
    else:
        portfolio_dd = None
    if state.portfolio.equity.known():
        current_equity = float(state.portfolio.equity.value)

    risk_state: Dict[str, Any] = {
        "requested_size": size,
        "consecutive_losses": consecutive_losses,
        "daily_pnl": daily_pnl,
        "exposure_pct": exposure,
        "signal_direction": signal.direction.value,
        "signal_confidence": signal.confidence,
    }

    if signal.direction == SignalDirection.NO_TRADE:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["signal_no_trade"],
            risk_state=risk_state,
        )
    if signal.direction == SignalDirection.HOLD:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["signal_hold"],
            risk_state=risk_state,
        )
    if signal.confidence < limits.confidence_threshold:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["confidence_below_threshold"],
            risk_state=risk_state,
        )
    if consecutive_losses >= limits.consecutive_loss_limit:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["consecutive_loss_protection"],
            risk_state=risk_state,
        )
    if daily_pnl <= -abs(limits.max_daily_loss):
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["max_daily_loss"],
            risk_state=risk_state,
        )

    if portfolio_dd is not None:
        risk_state["drawdown_pct"] = portfolio_dd
        if portfolio_dd >= limits.max_drawdown_pct:
            return RiskGateResult(
                verdict=RiskVerdict.REJECTED,
                approved_size=0.0,
                reasons=["max_drawdown"],
                risk_state=risk_state,
            )
    elif peak_equity > 0:
        dd = (peak_equity - current_equity) / peak_equity * 100.0
        risk_state["drawdown_pct"] = dd
        if dd >= limits.max_drawdown_pct:
            return RiskGateResult(
                verdict=RiskVerdict.REJECTED,
                approved_size=0.0,
                reasons=["max_drawdown"],
                risk_state=risk_state,
            )

    if exposure >= limits.max_exposure_pct:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["max_exposure"],
            risk_state=risk_state,
        )
    if state.liquidity.score.known() and float(state.liquidity.score.value) < limits.liquidity_min_score:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["liquidity_adjustment_reject"],
            risk_state=risk_state,
        )
    if not state.price.last.known():
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=["missing_price"],
            risk_state=risk_state,
        )

    if size > limits.max_position_size:
        size = limits.max_position_size
        reasons.append("capped_max_position_size")

    if capital is not None and capital > 0 and price and price > 0:
        max_affordable = capital / price
        if size > max_affordable:
            size = max_affordable
            reasons.append("capped_available_capital")

    # Volatility adjustment via atr_pct
    vol_mult = 1.0
    if state.volatility.atr_pct.known():
        atr_pct = float(state.volatility.atr_pct.value)
        if atr_pct > 4.0:
            vol_mult = max(0.25, 1.0 - (atr_pct - 4.0) * 0.15)
            reasons.append("volatility_adjustment")
    size *= vol_mult * limits.volatility_scale

    if state.liquidity.score.known():
        liq = float(state.liquidity.score.value)
        if liq < 55:
            size *= max(0.4, liq / 100.0)
            reasons.append("liquidity_adjustment_reduce")

    sl = tp = None
    if price and price > 0:
        if signal.direction == SignalDirection.BUY:
            sl = round(price * (1.0 - limits.stop_loss_pct), 6)
            tp = round(price * (1.0 + limits.take_profit_pct), 6)
        else:
            sl = round(price * (1.0 + limits.stop_loss_pct), 6)
            tp = round(price * (1.0 - limits.take_profit_pct), 6)

    if size <= 0:
        return RiskGateResult(
            verdict=RiskVerdict.REJECTED,
            approved_size=0.0,
            reasons=reasons or ["zero_size"],
            stop_loss=sl,
            take_profit=tp,
            risk_state=risk_state,
        )

    verdict = RiskVerdict.REDUCED if reasons else RiskVerdict.APPROVED
    risk_state["approved_size"] = size
    return RiskGateResult(
        verdict=verdict,
        approved_size=round(size, 6),
        reasons=reasons,
        stop_loss=sl,
        take_profit=tp,
        risk_state=risk_state,
    )
