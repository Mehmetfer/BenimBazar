"""Weighted confidence consensus — not simple majority vote."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from desk.models import AnalystVote


# Base weights — adjusted dynamically by regime fit and data quality.
_BASE_WEIGHTS: dict[str, float] = {
    "risk_manager": 1.35,
    "quant_analyst": 1.20,
    "regime_analyst": 1.15,
    "portfolio_manager": 1.10,
    "execution_manager": 1.05,
    "technical_analyst": 1.00,
    "market_analyst": 0.95,
    "fundamental_analyst": 0.90,
}

_BUY_DECISIONS = {"BUY", "STRONG_BUY", "AL", "BULLISH", "GO", "APPROVE", "ACCEPTABLE"}
_SELL_DECISIONS = {"SELL", "STRONG_SELL", "SAT", "BEARISH", "REDUCE"}
_NO_TRADE = {"NO_TRADE", "WAIT", "BEKLE", "VETO", "REJECT", "BLOCK", "HOLD"}


@dataclass
class ConsensusResult:
    decision: str
    confidence: float
    weighted_buy: float
    weighted_sell: float
    weighted_no_trade: float
    disagreement: float
    veto: bool
    veto_reason: str
    votes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "weighted_buy": round(self.weighted_buy, 4),
            "weighted_sell": round(self.weighted_sell, 4),
            "weighted_no_trade": round(self.weighted_no_trade, 4),
            "disagreement": round(self.disagreement, 4),
            "veto": self.veto,
            "veto_reason": self.veto_reason,
            "votes": self.votes,
        }


def _classify(decision: str) -> str:
    d = (decision or "").upper()
    if d in _BUY_DECISIONS:
        return "BUY"
    if d in _SELL_DECISIONS:
        return "SELL"
    return "NO_TRADE"


def _effective_weight(vote: AnalystVote, *, regime: str) -> float:
    w = _BASE_WEIGHTS.get(vote.analyst, 1.0) * max(0.1, float(vote.weight or 1.0))
    if vote.data_quality in {"UNKNOWN", "UNAVAILABLE"}:
        w *= 0.35
    elif vote.data_quality == "STALE":
        w *= 0.6
    conf = max(0.0, min(1.0, float(vote.confidence or 0)))
    w *= 0.5 + conf  # scale by confidence
    # Regime analyst gets boost when regime is clear
    if vote.analyst == "regime_analyst" and regime not in {"", "UNKNOWN", "UNCERTAIN"}:
        w *= 1.1
    return w


def compute_consensus(
    votes: list[AnalystVote],
    *,
    regime: str = "UNKNOWN",
    disagreement_threshold: float = 0.45,
) -> ConsensusResult:
    """Dynamic weighted consensus. Risk manager VETO overrides all."""
    serialized: list[dict[str, Any]] = []
    buy_w = sell_w = no_w = 0.0
    conf_sum = 0.0
    conf_n = 0

    for v in votes:
        eff = _effective_weight(v, regime=regime)
        bucket = _classify(v.decision)
        if bucket == "BUY":
            buy_w += eff
        elif bucket == "SELL":
            sell_w += eff
        else:
            no_w += eff
        conf_sum += float(v.confidence or 0) * eff
        conf_n += eff
        serialized.append({**v.to_dict(), "effective_weight": round(eff, 4), "bucket": bucket})

    # Risk manager explicit veto
    risk_votes = [v for v in votes if v.analyst == "risk_manager"]
    for rv in risk_votes:
        if str(rv.decision).upper() in {"VETO", "REJECT", "NO_TRADE", "BLOCK"} and float(rv.confidence or 0) >= 0.65:
            return ConsensusResult(
                decision="NO_TRADE",
                confidence=float(rv.confidence),
                weighted_buy=buy_w,
                weighted_sell=sell_w,
                weighted_no_trade=no_w + 2.0,
                disagreement=1.0,
                veto=True,
                veto_reason=rv.reason or rv.risk or "risk_manager_veto",
                votes=serialized,
            )

    total = buy_w + sell_w + no_w
    if total <= 0:
        return ConsensusResult(
            decision="NO_TRADE",
            confidence=0.0,
            weighted_buy=0.0,
            weighted_sell=0.0,
            weighted_no_trade=0.0,
            disagreement=0.0,
            veto=False,
            veto_reason="",
            votes=serialized,
        )

    # Disagreement: how split are the buckets
    shares = [buy_w / total, sell_w / total, no_w / total]
    dominant = max(shares)
    disagreement = 1.0 - dominant

    if disagreement >= disagreement_threshold:
        return ConsensusResult(
            decision="NO_TRADE",
            confidence=conf_sum / conf_n if conf_n else 0.0,
            weighted_buy=buy_w,
            weighted_sell=sell_w,
            weighted_no_trade=no_w,
            disagreement=disagreement,
            veto=False,
            veto_reason="model_disagreement",
            votes=serialized,
        )

    if buy_w >= sell_w and buy_w >= no_w and buy_w / total >= 0.42:
        decision = "BUY"
    elif sell_w > buy_w and sell_w > no_w and sell_w / total >= 0.42:
        decision = "SELL"
    else:
        decision = "NO_TRADE"

    confidence = conf_sum / conf_n if conf_n else 0.0
    return ConsensusResult(
        decision=decision,
        confidence=confidence,
        weighted_buy=buy_w,
        weighted_sell=sell_w,
        weighted_no_trade=no_w,
        disagreement=disagreement,
        veto=False,
        veto_reason="",
        votes=serialized,
    )
