"""Decision confidence — necessary but never sufficient for execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.reasons import RC_LOW_CONFIDENCE, DecisionReason
from decision.ade.states import DecisionAction


@dataclass
class ConfidenceResult:
    decision_confidence: float
    threshold: float
    passes_threshold: bool
    components: dict[str, float]
    reason: DecisionReason

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason"] = self.reason.to_dict()
        return d


def compute_decision_confidence(
    *,
    signal_agreement: float,
    data_freshness: float,
    regime_clarity: float,
    provider_reliability: float,
    ev_quality: float,
    limits: ImmutableSafetyLimits,
) -> ConfidenceResult:
    """Weighted confidence in [0, 1]. Below threshold → prefer NO_TRADE upstream."""
    comps = {
        "signal_agreement": _clip(signal_agreement),
        "data_freshness": _clip(data_freshness),
        "regime_clarity": _clip(regime_clarity),
        "provider_reliability": _clip(provider_reliability),
        "ev_quality": _clip(ev_quality),
    }
    conf = (
        0.30 * comps["signal_agreement"]
        + 0.20 * comps["data_freshness"]
        + 0.15 * comps["regime_clarity"]
        + 0.20 * comps["provider_reliability"]
        + 0.15 * comps["ev_quality"]
    )
    conf = _clip(conf)
    reason = DecisionReason(stage="CONFIDENCE")
    passes = conf >= limits.confidence_threshold
    if not passes:
        reason.add(
            RC_LOW_CONFIDENCE,
            "confidence below threshold",
            confidence=conf,
            threshold=limits.confidence_threshold,
        )
    return ConfidenceResult(
        decision_confidence=conf,
        threshold=limits.confidence_threshold,
        passes_threshold=passes,
        components=comps,
        reason=reason,
    )


def apply_confidence_gate(action: DecisionAction, conf: ConfidenceResult) -> DecisionAction:
    """Confidence alone never authorizes orders; low confidence forces NO_TRADE."""
    if action in {DecisionAction.BUY, DecisionAction.SELL, DecisionAction.REDUCE} and not conf.passes_threshold:
        return DecisionAction.NO_TRADE
    return action


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
