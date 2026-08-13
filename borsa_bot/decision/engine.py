"""GÖREV 15–16 — Decision engine with NO_TRADE intelligence (paper only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from decision.market_state import DataQuality, MarketState
from decision.observe import observe_market
from decision.regime import classify_trading_regime
from decision.risk_gate import RiskLimits, RiskVerdict, evaluate_risk
from decision.signals import CompositeSignal, SignalDirection, fuse_signals


class DecisionAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


@dataclass
class DecisionOutput:
    decision: DecisionAction
    confidence: float
    reason: str
    evidence: List[str] = field(default_factory=list)
    risk_state: Dict[str, Any] = field(default_factory=dict)
    position_size: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    no_trade_reasons: List[str] = field(default_factory=list)
    market_state: Optional[Dict[str, Any]] = None
    regime: Optional[Dict[str, Any]] = None
    composite_signal: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    symbol: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "evidence": list(self.evidence),
            "risk_state": dict(self.risk_state),
            "position_size": self.position_size,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "no_trade_reasons": list(self.no_trade_reasons),
            "market_state": self.market_state,
            "regime": self.regime,
            "composite_signal": self.composite_signal,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "live_trading": False,
            "execution_mode": "PAPER",
        }


def _is_stale(state: MarketState) -> bool:
    return state.price.last.quality in (DataQuality.STALE, DataQuality.MISSING)


def _uniq(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def decide_from_state(
    state: MarketState,
    *,
    requested_size: float = 10.0,
    limits: Optional[RiskLimits] = None,
    consecutive_losses: int = 0,
    daily_pnl: float = 0.0,
    peak_equity: float = 10000.0,
    current_equity: float = 10000.0,
    calibration_hint: Optional[str] = None,
    strategy_memory_hint: Optional[str] = None,
) -> DecisionOutput:
    """Full F6 chain on a normalized MarketState (paper decisions only)."""
    ts = datetime.now(timezone.utc).isoformat()
    regime = classify_trading_regime(state)
    unknowns = state.collect_unknowns()
    evidence: List[str] = []
    no_trade: List[str] = []

    # Core required fields for a tradeable decision
    core_unknown = [
        u
        for u in unknowns
        if u.endswith(".last")
        or u.endswith(".label")
        or u.endswith(".rsi")
        or "liquidity.score" in u
        or u == "last"  # price.last walks as "last"
    ]
    # price.last is collected as "last" (see MarketState.collect_unknowns)
    price_missing = not state.price.last.known()
    if price_missing or (not state.trend.label.known() and not state.momentum.rsi.known()):
        no_trade.append("missing_data")
        evidence.append(f"unknown_fields={len(unknowns)}")
    elif core_unknown and len(unknowns) >= 8:
        no_trade.append("missing_data")
        evidence.append(f"sparse_observation unknowns={len(unknowns)}")

    if _is_stale(state):
        no_trade.append("stale_market_data")
        evidence.append("price_stale")

    if regime.regime.value == "HIGH_VOLATILITY":
        no_trade.append("high_volatility")
        evidence.extend(regime.evidence[:2])
    if regime.regime.value == "LOW_LIQUIDITY":
        no_trade.append("low_liquidity")
        evidence.extend(regime.evidence[:2])
    if regime.regime.value == "UNKNOWN":
        no_trade.append("market_regime_mismatch")
        evidence.append("regime_unknown")

    signal = fuse_signals(state, regime)
    evidence.append(f"composite={signal.direction.value}:{signal.score:.3f}")
    if signal.conflict:
        no_trade.append("conflicting_signals")
        evidence.extend(signal.conflict_reasons)

    if calibration_hint == "OVERCONFIDENT":
        evidence.append(f"calibration={calibration_hint}")
        signal = CompositeSignal(
            direction=signal.direction,
            score=signal.score,
            confidence=min(signal.confidence, 0.5),
            conflict=signal.conflict,
            conflict_reasons=list(signal.conflict_reasons) + ["calibration_overconfident_dampen"],
            components=signal.components,
            timestamp=signal.timestamp,
        )
    if strategy_memory_hint:
        evidence.append(f"strategy_memory={strategy_memory_hint}")

    if signal.direction == SignalDirection.NO_TRADE:
        if "insufficient_confidence" in signal.conflict_reasons:
            no_trade.append("insufficient_confidence")
        else:
            no_trade.append("signal_no_trade")

    risk = evaluate_risk(
        state,
        signal,
        requested_size=requested_size,
        limits=limits,
        consecutive_losses=consecutive_losses,
        daily_pnl=daily_pnl,
        peak_equity=peak_equity,
        current_equity=current_equity,
    )
    evidence.append(f"risk={risk.verdict.value}")
    if risk.verdict == RiskVerdict.REJECTED:
        no_trade.append("risk_limit")
        no_trade.extend(risk.reasons)
        if "max_drawdown" in risk.reasons:
            no_trade.append("drawdown_protection")

    early_block = bool(
        set(no_trade)
        & {
            "missing_data",
            "stale_market_data",
            "high_volatility",
            "low_liquidity",
            "market_regime_mismatch",
            "conflicting_signals",
            "insufficient_confidence",
            "drawdown_protection",
        }
    )

    if early_block or signal.direction == SignalDirection.NO_TRADE or risk.verdict == RiskVerdict.REJECTED:
        uniq = _uniq(no_trade)
        reason = ";".join(uniq) if uniq else "no_trade"
        return DecisionOutput(
            decision=DecisionAction.NO_TRADE,
            confidence=min(signal.confidence, 0.4),
            reason=reason,
            evidence=evidence,
            risk_state=risk.to_dict(),
            position_size=0.0,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            no_trade_reasons=uniq,
            market_state=state.to_dict(),
            regime=regime.to_dict(),
            composite_signal=signal.to_dict(),
            timestamp=ts,
            symbol=state.symbol,
        )

    action = DecisionAction.BUY if signal.direction == SignalDirection.BUY else DecisionAction.SELL
    return DecisionOutput(
        decision=action,
        confidence=signal.confidence,
        reason=f"approved_{action.value.lower()}",
        evidence=evidence,
        risk_state=risk.to_dict(),
        position_size=risk.approved_size,
        stop_loss=risk.stop_loss,
        take_profit=risk.take_profit,
        no_trade_reasons=[],
        market_state=state.to_dict(),
        regime=regime.to_dict(),
        composite_signal=signal.to_dict(),
        timestamp=ts,
        symbol=state.symbol,
    )


def decide(
    provider: Any,
    ledger: Any,
    symbol: str,
    **kwargs: Any,
) -> DecisionOutput:
    state = observe_market(provider=provider, ledger=ledger, symbol=symbol)
    return decide_from_state(state, **kwargs)
