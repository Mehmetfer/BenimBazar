"""Change risk scoring — trading-critical paths auto-elevate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from self_improvement.invariants import HIGH_RISK_PATH_MARKERS, path_allowed_for_auto_impl


@dataclass
class RiskAssessment:
    score: int  # 0-100
    band: str
    reasons: list[str]
    requires_expanded_suite: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def band_for(score: int) -> str:
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "MODERATE"
    if score <= 60:
        return "HIGH"
    if score <= 80:
        return "VERY HIGH"
    return "CRITICAL"


def assess_change_risk(paths: list[str], *, touches_tests: bool = False, category: str = "") -> RiskAssessment:
    score = 10
    reasons: list[str] = ["base change"]
    for p in paths:
        pl = p.replace("\\", "/").lower()
        if not path_allowed_for_auto_impl(p):
            score = max(score, 85)
            reasons.append(f"non-allowlisted path: {p}")
        for marker in HIGH_RISK_PATH_MARKERS:
            if marker.lower() in pl:
                score = max(score, 70)
                reasons.append(f"high-risk marker {marker!r} in {p}")
        if pl.endswith(".py") and "test_" not in pl and not touches_tests:
            score += 5
    if category.lower() in {"safety", "security", "domain_invariant"}:
        score = max(score, 55)
        reasons.append(f"category={category}")
    if touches_tests:
        score = max(5, score - 10)
        reasons.append("includes tests")
    score = max(0, min(100, score))
    band = band_for(score)
    return RiskAssessment(
        score=score,
        band=band,
        reasons=reasons,
        requires_expanded_suite=score >= 41,
    )
