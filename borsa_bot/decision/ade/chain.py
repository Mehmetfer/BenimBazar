"""Decision chain stages — MARKET DATA → … → POST-TRADE VERIFICATION."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from decision.ade.confidence import apply_confidence_gate, compute_decision_confidence
from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.reasons import (
    RC_DATA_INVALID,
    RC_DATA_STALE,
    RC_EV_INSUFFICIENT,
    RC_EV_POSITIVE,
    RC_EXPOSURE_HIGH,
    RC_KILL_SWITCH,
    RC_MULTI_SIGNAL_OK,
    RC_PROVIDER_UNCERTAIN,
    RC_REGIME_SUPPORT,
    RC_REGIME_UNCERTAIN,
    RC_RISK_REWARD_POOR,
    RC_SIGNAL_CONFLICT,
    RC_SLIPPAGE_HIGH,
    DecisionReason,
)
from decision.ade.sizing import PositionSizeResult, calculate_position_size
from decision.ade.states import DecisionAction


class ChainStage(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    DATA_VALIDATION = "DATA_VALIDATION"
    MARKET_REGIME = "MARKET_REGIME"
    SIGNAL_ANALYSIS = "SIGNAL_ANALYSIS"
    MULTI_SIGNAL_CONFIRMATION = "MULTI_SIGNAL_CONFIRMATION"
    PORTFOLIO_STATE = "PORTFOLIO_STATE"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    POSITION_SIZING = "POSITION_SIZING"
    EXPECTED_VALUE = "EXPECTED_VALUE"
    COST_SLIPPAGE = "COST_SLIPPAGE"
    DECISION_ENGINE = "DECISION_ENGINE"
    SAFETY_GATE = "SAFETY_GATE"
    EXECUTION = "EXECUTION"
    POST_TRADE_VERIFICATION = "POST_TRADE_VERIFICATION"


CHAIN_ORDER: list[ChainStage] = list(ChainStage)


@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    timestamp: str = ""
    provider: str = "UNKNOWN"
    provider_ok: bool = False
    data_valid: bool = False
    data_fresh: bool = False
    regime: str = "UNKNOWN"
    signals: list[str] = field(default_factory=list)
    equity: float = 100_000.0
    cash: float = 100_000.0
    exposure_pct: float = 0.0
    daily_loss_pct: float = 0.0
    open_qty: float = 0.0
    expected_value: float | None = None
    risk_reward: float | None = None
    stop_distance_pct: float = 2.0
    risk_pct: float = 0.5
    slippage_bps: float = 5.0
    cost_bps: float = 2.0
    provider_reliability: float = 0.9
    sector: str = "X"


@dataclass
class ChainResult:
    action: DecisionAction
    reason: DecisionReason
    stages: list[str] = field(default_factory=list)
    stage_details: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    size: Optional[PositionSizeResult] = None
    candidate_actions: list[str] = field(default_factory=list)
    halted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "action": self.action.value,
            "reason": self.reason.to_dict(),
            "stages": self.stages,
            "stage_details": self.stage_details,
            "confidence": self.confidence,
            "candidate_actions": self.candidate_actions,
            "halted_at": self.halted_at,
            "size": self.size.to_dict() if self.size else None,
        }
        return d


def _no_trade(result: ChainResult, code: str, msg: str, stage: ChainStage, **inputs: Any) -> ChainResult:
    result.action = DecisionAction.NO_TRADE
    result.reason.stage = stage.value
    result.reason.add(code, msg, **inputs)
    result.halted_at = stage.value
    return result


def run_decision_chain(snap: MarketSnapshot, limits: ImmutableSafetyLimits) -> ChainResult:
    """Full autonomous decision chain ending in a DecisionAction (+ sizing)."""
    reason = DecisionReason(stage=ChainStage.DECISION_ENGINE.value)
    result = ChainResult(action=DecisionAction.NO_TRADE, reason=reason)

    # 1 MARKET DATA
    result.stages.append(ChainStage.MARKET_DATA.value)
    result.stage_details["market_data"] = {
        "symbol": snap.symbol,
        "price": snap.price,
        "provider": snap.provider,
        "timestamp": snap.timestamp,
    }
    if snap.price <= 0 or not snap.symbol:
        return _no_trade(result, RC_DATA_INVALID, "missing market data", ChainStage.MARKET_DATA)

    # 2 DATA VALIDATION
    result.stages.append(ChainStage.DATA_VALIDATION.value)
    if not snap.data_valid:
        return _no_trade(result, RC_DATA_INVALID, "data validation failed", ChainStage.DATA_VALIDATION)
    if not snap.data_fresh:
        return _no_trade(result, RC_DATA_STALE, "data stale", ChainStage.DATA_VALIDATION)
    if not snap.provider_ok or snap.provider.upper() in {"UNKNOWN", "REQUIRED", "UNAVAILABLE"}:
        return _no_trade(
            result,
            RC_PROVIDER_UNCERTAIN,
            "provider uncertain",
            ChainStage.DATA_VALIDATION,
            provider=snap.provider,
        )
    result.stage_details["data_validation"] = {"ok": True, "provider": snap.provider}

    # 3 MARKET REGIME
    result.stages.append(ChainStage.MARKET_REGIME.value)
    regime = (snap.regime or "UNKNOWN").upper()
    if regime in {"UNKNOWN", "", "UNCERTAIN"}:
        return _no_trade(result, RC_REGIME_UNCERTAIN, "regime uncertain", ChainStage.MARKET_REGIME)
    result.stage_details["regime"] = regime
    reason.add(RC_REGIME_SUPPORT, "regime classified", regime=regime)

    # 4 SIGNAL ANALYSIS
    result.stages.append(ChainStage.SIGNAL_ANALYSIS.value)
    signals = [s.upper() for s in snap.signals]
    result.stage_details["signals"] = signals
    if not signals:
        return _no_trade(result, RC_SIGNAL_CONFLICT, "no signals", ChainStage.SIGNAL_ANALYSIS)

    buys = sum(1 for s in signals if s in {"BUY", "STRONG_BUY", "AL", "LONG"})
    sells = sum(1 for s in signals if s in {"SELL", "STRONG_SELL", "SAT", "SHORT"})
    holds = sum(1 for s in signals if s in {"HOLD", "WAIT", "BEKLE", "WATCH"})
    exits = sum(1 for s in signals if s in {"EXIT", "CLOSE"})
    reduces = sum(1 for s in signals if s in {"REDUCE"})

    # 5 MULTI-SIGNAL CONFIRMATION
    result.stages.append(ChainStage.MULTI_SIGNAL_CONFIRMATION.value)
    if buys and sells:
        return _no_trade(result, RC_SIGNAL_CONFLICT, "buy/sell conflict", ChainStage.MULTI_SIGNAL_CONFIRMATION)
    if buys >= 2:
        candidate = DecisionAction.BUY
        reason.add(RC_MULTI_SIGNAL_OK, "multi-buy confirmed", count=buys)
    elif sells >= 2:
        candidate = DecisionAction.SELL
        reason.add(RC_MULTI_SIGNAL_OK, "multi-sell confirmed", count=sells)
    elif exits >= 1 and snap.open_qty > 0:
        candidate = DecisionAction.EXIT
    elif reduces >= 1 and snap.open_qty > 0:
        candidate = DecisionAction.REDUCE
    elif buys == 1 and sells == 0:
        candidate = DecisionAction.WAIT  # single signal → wait for confirmation
        result.candidate_actions = [DecisionAction.BUY.value, DecisionAction.WAIT.value]
        result.stages.append(ChainStage.DECISION_ENGINE.value)
        result.action = DecisionAction.WAIT
        reason.add(RC_SIGNAL_CONFLICT, "single unconfirmed signal → WAIT")
        result.halted_at = ChainStage.MULTI_SIGNAL_CONFIRMATION.value
        return result
    elif holds and not buys and not sells:
        candidate = DecisionAction.HOLD
    else:
        return _no_trade(result, RC_SIGNAL_CONFLICT, "unresolved signals", ChainStage.MULTI_SIGNAL_CONFIRMATION)

    result.candidate_actions = [candidate.value]

    # 6 PORTFOLIO STATE
    result.stages.append(ChainStage.PORTFOLIO_STATE.value)
    result.stage_details["portfolio"] = {
        "equity": snap.equity,
        "exposure_pct": snap.exposure_pct,
        "daily_loss_pct": snap.daily_loss_pct,
        "open_qty": snap.open_qty,
    }
    if snap.exposure_pct > limits.hard_max_exposure_pct and candidate in {DecisionAction.BUY}:
        return _no_trade(result, RC_EXPOSURE_HIGH, "exposure too high", ChainStage.PORTFOLIO_STATE)

    # 7 RISK ANALYSIS
    result.stages.append(ChainStage.RISK_ANALYSIS.value)
    if snap.daily_loss_pct >= limits.hard_max_daily_loss_pct:
        return _no_trade(result, RC_EXPOSURE_HIGH, "daily loss limit", ChainStage.RISK_ANALYSIS)
    if limits.kill_switch_active:
        return _no_trade(result, RC_KILL_SWITCH, "kill switch", ChainStage.RISK_ANALYSIS)

    rr = snap.risk_reward
    if candidate in {DecisionAction.BUY, DecisionAction.SELL} and rr is not None and rr < 1.0:
        return _no_trade(result, RC_RISK_REWARD_POOR, "poor RR", ChainStage.RISK_ANALYSIS, rr=rr)

    # 8 POSITION SIZING
    result.stages.append(ChainStage.POSITION_SIZING.value)
    size = calculate_position_size(
        equity=snap.equity,
        price=snap.price,
        risk_pct=snap.risk_pct,
        stop_distance_pct=snap.stop_distance_pct,
        limits=limits,
        current_exposure_pct=snap.exposure_pct,
        confidence=1.0,
    )
    result.size = size
    if candidate in {DecisionAction.BUY, DecisionAction.SELL} and size.capped_size <= 0:
        return _no_trade(result, RC_EV_INSUFFICIENT, "size zero", ChainStage.POSITION_SIZING)

    # EXIT/REDUCE size from open qty
    if candidate is DecisionAction.EXIT and snap.open_qty > 0:
        result.size = PositionSizeResult(
            calculated_size=snap.open_qty,
            capped_size=min(snap.open_qty, limits.hard_max_position_size),
            notional=min(snap.open_qty, limits.hard_max_position_size) * snap.price,
            within_hard_max=True,
            reason=size.reason,
        )
    if candidate is DecisionAction.REDUCE and snap.open_qty > 0:
        half = snap.open_qty / 2.0
        result.size = PositionSizeResult(
            calculated_size=half,
            capped_size=min(half, limits.hard_max_position_size),
            notional=min(half, limits.hard_max_position_size) * snap.price,
            within_hard_max=True,
            reason=size.reason,
        )

    # 9 EXPECTED VALUE
    result.stages.append(ChainStage.EXPECTED_VALUE.value)
    ev = snap.expected_value
    result.stage_details["expected_value"] = ev
    if candidate in {DecisionAction.BUY, DecisionAction.SELL}:
        if ev is None or ev < limits.min_expected_value:
            return _no_trade(result, RC_EV_INSUFFICIENT, "EV insufficient", ChainStage.EXPECTED_VALUE, ev=ev)
        reason.add(RC_EV_POSITIVE, "EV ok", ev=ev)

    # 10 COST / SLIPPAGE
    result.stages.append(ChainStage.COST_SLIPPAGE.value)
    slip = snap.slippage_bps + snap.cost_bps
    result.stage_details["cost_slippage_bps"] = slip
    if slip > limits.max_slippage_bps and candidate in {DecisionAction.BUY, DecisionAction.SELL}:
        return _no_trade(result, RC_SLIPPAGE_HIGH, "slippage/cost high", ChainStage.COST_SLIPPAGE, slip=slip)

    # Confidence
    agreement = 1.0 if (buys >= 2 or sells >= 2 or candidate in {DecisionAction.EXIT, DecisionAction.REDUCE, DecisionAction.HOLD}) else 0.4
    conf = compute_decision_confidence(
        signal_agreement=agreement,
        data_freshness=1.0 if snap.data_fresh else 0.0,
        regime_clarity=0.8 if regime not in {"NEUTRAL", "SIDEWAYS"} else 0.55,
        provider_reliability=snap.provider_reliability,
        ev_quality=0.8 if (ev or 0) > 0 else 0.3,
        limits=limits,
    )
    result.confidence = conf.decision_confidence
    result.stage_details["confidence"] = conf.to_dict()

    # 11 DECISION ENGINE
    result.stages.append(ChainStage.DECISION_ENGINE.value)
    final = apply_confidence_gate(candidate, conf)
    if final is DecisionAction.NO_TRADE and candidate is not DecisionAction.NO_TRADE:
        return _no_trade(result, conf.reason.codes[0] if conf.reason.codes else "LOW_CONFIDENCE", "confidence gate", ChainStage.DECISION_ENGINE)

    result.action = final
    reason.stage = ChainStage.DECISION_ENGINE.value
    return result
