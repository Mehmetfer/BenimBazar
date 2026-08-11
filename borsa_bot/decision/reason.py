"""Phase 3 — Deterministic AI reasoning over structured scan features (no LLM fiction)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from decision.opportunity import ENTRY_LIKE, RankedOpportunity

# Local reason-code strings (avoid circular import with autonomous.engine)
RC_DATA_STALE = "DATA_STALE"
RC_MTF_CONFLICT = "MTF_CONFLICT"
RC_MTF_ALIGNMENT = "MTF_ALIGNMENT"
RC_REGIME_SUPPORT = "REGIME_SUPPORT"
RC_LIQUIDITY_OK = "LIQUIDITY_OK"
RC_EV_POSITIVE = "EXPECTED_VALUE_POSITIVE"
RC_TREND = "TREND_CONFIRMED"
RC_VOLUME = "VOLUME_CONFIRMATION"
RC_NEG_EV = "NEGATIVE_EXPECTED_VALUE"


STRATEGY_BY_REGIME = {
    "STRONG_BULL": "TREND_FOLLOWING",
    "BULL": "TREND_FOLLOWING",
    "NEUTRAL": "MEAN_REVERSION",
    "SIDEWAYS": "MEAN_REVERSION",
    "BEAR": "PULLBACK",
    "STRONG_BEAR": "MOMENTUM",  # typically defensive / short bias → WAIT preferred
}


@dataclass
class ReasoningResult:
    decision_id: str
    symbol: str
    market_type: str
    action: str
    confidence: float | None
    probability: float | None  # calibrated only when known; else None
    model_score: float | None
    opportunity_score: float
    expected_value: float | None
    expected_return_pct: float | None
    expected_risk_pct: float | None
    risk_reward: float | None
    regime: str | None
    strategy: str
    mtf_label: str
    reason_codes: list[str] = field(default_factory=list)
    counter_argument: str | None = None
    invalidations: list[str] = field(default_factory=list)
    tree_path: list[str] = field(default_factory=list)
    can_trade_proposal: bool = False
    note: str = "confidence ≠ calibrated probability"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mtf_label(mtf: dict[str, Any]) -> str:
    if not mtf:
        return "UNKNOWN"
    vals = {str(v).upper() for v in mtf.values()}
    buys = any(v in {"BUY", "BULL", "BULLISH", "UP", "LONG"} for v in vals)
    sells = any(v in {"SELL", "BEAR", "BEARISH", "DOWN", "SHORT"} for v in vals)
    if buys and sells:
        return "SHORT_TERM_MIXED_LONG_TERM_CONFLICT" if "1d" in {k.lower() for k in mtf} else "MTF_CONFLICT"
    if buys:
        return "MTF_ALIGNED_BULLISH"
    if sells:
        return "MTF_ALIGNED_BEARISH"
    return "MTF_NEUTRAL"


def reason_over_opportunity(
    opp: RankedOpportunity,
    *,
    decision_id: str,
    context: dict[str, Any],
    row: dict[str, Any] | None = None,
) -> ReasoningResult:
    """Decision tree: DATA → REGIME → MTF → LIQ → SPREAD → EV → propose action.

    Output is a PROPOSAL only. RiskEngine / PreTradeGate may still REJECT.
    """
    tree: list[str] = []
    codes: list[str] = []
    invalidations: list[str] = []
    action = opp.action
    row = row or {}

    # 1 DATA VALID
    if not context.get("data_valid", True):
        tree.append("DATA_VALID=NO→NO_TRADE")
        return ReasoningResult(
            decision_id=decision_id,
            symbol=opp.symbol,
            market_type=opp.market_type,
            action="NO_TRADE",
            confidence=0.0,
            probability=None,
            model_score=opp.model_score,
            opportunity_score=opp.opportunity_score,
            expected_value=opp.expected_value,
            expected_return_pct=opp.expected_return_pct,
            expected_risk_pct=opp.expected_risk_pct,
            risk_reward=opp.risk_reward,
            regime=opp.regime or context.get("market_regime"),
            strategy="NONE",
            mtf_label=_mtf_label(opp.mtf),
            reason_codes=[RC_DATA_STALE, "DATA_INVALID"],
            counter_argument="Data invalid or unavailable",
            invalidations=["DATA_FAILURE"],
            tree_path=tree,
            can_trade_proposal=False,
            note="NO TRADE — data validity failed",
        )
    tree.append("DATA_VALID=YES")

    # Insufficient history
    note = str(row.get("note") or "")
    if "INSUFFICIENT" in note.upper() or row.get("insufficient_history"):
        tree.append("ENOUGH_HISTORY=NO→WAIT")
        return ReasoningResult(
            decision_id=decision_id,
            symbol=opp.symbol,
            market_type=opp.market_type,
            action="WAIT",
            confidence=opp.confidence,
            probability=None,
            model_score=opp.model_score,
            opportunity_score=opp.opportunity_score,
            expected_value=opp.expected_value,
            expected_return_pct=opp.expected_return_pct,
            expected_risk_pct=opp.expected_risk_pct,
            risk_reward=opp.risk_reward,
            regime=opp.regime or context.get("market_regime"),
            strategy="NONE",
            mtf_label=_mtf_label(opp.mtf),
            reason_codes=["INSUFFICIENT_HISTORY"],
            counter_argument="Need more bars before edge claim",
            invalidations=["INSUFFICIENT_HISTORY"],
            tree_path=tree,
            can_trade_proposal=False,
        )
    tree.append("ENOUGH_HISTORY=YES")

    regime = str(opp.regime or context.get("market_regime") or "UNKNOWN").upper()
    strategy = STRATEGY_BY_REGIME.get(regime, "TREND_FOLLOWING")
    mtf_lab = _mtf_label(opp.mtf)

    if "CONFLICT" in mtf_lab:
        codes.append(RC_MTF_CONFLICT)
        tree.append("MTF_ALIGNED=NO→LOWER_CONFIDENCE")
        if action in {"STRONG_BUY"}:
            action = "BUY"
        if action in ENTRY_LIKE and regime in {"BEAR", "STRONG_BEAR"}:
            action = "WAIT"
            codes.append("BEAR_REGIME")
    else:
        if "BULLISH" in mtf_lab:
            codes.append(RC_MTF_ALIGNMENT)
        tree.append("MTF_ALIGNED=CHECK")

    if regime in {"BEAR", "STRONG_BEAR"} and action in ENTRY_LIKE:
        codes.append("BEAR_REGIME")
        tree.append("REGIME_SUPPORTIVE=NO→LOWER_CONFIDENCE")
        # Require stronger edge in bear
        if (opp.expected_value or 0) < 0.5:
            action = "NO_TRADE"
            codes.append(RC_NEG_EV)
            tree.append("BEAR+WEAK_EV→NO_TRADE")
    else:
        tree.append("REGIME_SUPPORTIVE=YES_OR_NEUTRAL")
        if action in ENTRY_LIKE:
            codes.append(RC_REGIME_SUPPORT)

    if not opp.liquidity_ok:
        tree.append("LIQUIDITY_OK=NO→NO_TRADE")
        return ReasoningResult(
            decision_id=decision_id,
            symbol=opp.symbol,
            market_type=opp.market_type,
            action="NO_TRADE",
            confidence=opp.confidence,
            probability=None,
            model_score=opp.model_score,
            opportunity_score=opp.opportunity_score,
            expected_value=opp.expected_value,
            expected_return_pct=opp.expected_return_pct,
            expected_risk_pct=opp.expected_risk_pct,
            risk_reward=opp.risk_reward,
            regime=regime,
            strategy=strategy,
            mtf_label=mtf_lab,
            reason_codes=codes + ["LOW_LIQUIDITY"],
            counter_argument="Liquidity too weak for controlled entry",
            invalidations=["LOW_LIQUIDITY"],
            tree_path=tree,
            can_trade_proposal=False,
        )
    tree.append("LIQUIDITY_OK=YES")
    codes.append(RC_LIQUIDITY_OK)

    if not opp.spread_ok:
        tree.append("SPREAD_OK=NO→NO_TRADE")
        return ReasoningResult(
            decision_id=decision_id,
            symbol=opp.symbol,
            market_type=opp.market_type,
            action="NO_TRADE",
            confidence=opp.confidence,
            probability=None,
            model_score=opp.model_score,
            opportunity_score=opp.opportunity_score,
            expected_value=opp.expected_value,
            expected_return_pct=opp.expected_return_pct,
            expected_risk_pct=opp.expected_risk_pct,
            risk_reward=opp.risk_reward,
            regime=regime,
            strategy=strategy,
            mtf_label=mtf_lab,
            reason_codes=codes + ["HIGH_SPREAD"],
            counter_argument="Spread expands edge away",
            invalidations=["SPREAD_EXPANDED"],
            tree_path=tree,
            can_trade_proposal=False,
        )
    tree.append("SPREAD_OK=YES")

    ev = opp.expected_value
    if ev is not None and ev <= 0 and action in ENTRY_LIKE:
        tree.append("EV_POSITIVE=NO→NO_TRADE")
        action = "NO_TRADE"
        codes.append("NEGATIVE_EXPECTED_VALUE")
    elif ev is not None and ev > 0:
        tree.append("EV_POSITIVE=YES")
        codes.append(RC_EV_POSITIVE)
    else:
        tree.append("EV_POSITIVE=UNKNOWN")
        if action in ENTRY_LIKE:
            # No edge estimate → do not force trade
            action = "WAIT"
            codes.append("NO_CLEAR_EDGE")
            tree.append("NO_CLEAR_EDGE→WAIT")

    # Positive supporting codes from row
    if action in ENTRY_LIKE:
        codes.append(RC_TREND)
        if float(row.get("volume_score") or (row.get("scores") or {}).get("volume") or 0) >= 60:
            codes.append(RC_VOLUME)

    # Self-critique / counter argument
    counter = _counter_argument(action, regime, mtf_lab, ev)
    invalidations = _invalidations(action)

    conf = opp.confidence
    if conf is not None and "CONFLICT" in mtf_lab:
        conf = round(max(0.0, float(conf) * 0.75), 1)
    if conf is not None and regime in {"BEAR", "STRONG_BEAR"} and action in ENTRY_LIKE:
        conf = round(max(0.0, float(conf) * 0.8), 1)

    can_propose = action in ENTRY_LIKE or action in {"SELL", "STRONG_SELL", "SAT"}
    tree.append(f"FINAL={action}")

    # Deduplicate codes
    uniq: list[str] = []
    for c in codes:
        if c not in uniq:
            uniq.append(c)

    return ReasoningResult(
        decision_id=decision_id,
        symbol=opp.symbol,
        market_type=opp.market_type,
        action=action,
        confidence=conf,
        probability=None,  # never claim calibrated probability here
        model_score=opp.model_score,
        opportunity_score=opp.opportunity_score,
        expected_value=ev,
        expected_return_pct=opp.expected_return_pct,
        expected_risk_pct=opp.expected_risk_pct,
        risk_reward=opp.risk_reward,
        regime=regime,
        strategy=strategy,
        mtf_label=mtf_lab,
        reason_codes=uniq,
        counter_argument=counter,
        invalidations=invalidations,
        tree_path=tree,
        can_trade_proposal=can_propose and action not in {"NO_TRADE", "WAIT", "BLOCKED"},
        note="Proposal only — RiskEngine + PreTradeGate are authoritative",
    )


def _counter_argument(action: str, regime: str, mtf: str, ev: float | None) -> str:
    if action in ENTRY_LIKE:
        parts = []
        if regime in {"BEAR", "STRONG_BEAR"}:
            parts.append("Bear regime can invalidate long edge")
        if "CONFLICT" in mtf:
            parts.append("Higher TF conflict may reverse short-term long")
        if ev is not None and ev < 1.0:
            parts.append("Thin expected value vs costs/slippage")
        parts.append("Breakout/volume failure or spread expansion")
        return "; ".join(parts)
    if action in {"SELL", "STRONG_SELL", "SAT"}:
        return "Short-covering bounce or regime flip to risk-on"
    return "No actionable edge — waiting is valid"


def _invalidations(action: str) -> list[str]:
    if action in ENTRY_LIKE:
        return [
            "VOLUME_FAILURE",
            "BREAKOUT_FAILURE",
            "REGIME_CHANGED",
            "SUPPORT_LOSS",
            "SPREAD_EXPANDED",
            "MARKET_REVERSAL",
        ]
    if action in {"SELL", "STRONG_SELL", "SAT"}:
        return ["SHORT_SQUEEZE", "REGIME_CHANGED", "RESISTANCE_HOLD"]
    return ["DATA_STALE", "REGIME_CHANGED"]
