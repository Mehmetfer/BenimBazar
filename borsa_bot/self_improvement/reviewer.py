"""Second-pass REVIEWER for SI changes (distinct from IMPLEMENTER)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from self_improvement.invariants import FROZEN_PRODUCTION_INVARIANTS, path_allowed_for_auto_impl


@dataclass
class ReviewResult:
    approved: bool
    questions: dict[str, str]
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_change(
    *,
    paths: list[str],
    diff_summary: str,
    risk_score: int,
    has_tests: bool,
    measurable_benefit: bool,
    touches_frozen_invariant: bool = False,
) -> ReviewResult:
    q = {
        "necessary": "unknown",
        "simpler_exists": "consider",
        "regression_risk": "elevated" if risk_score >= 41 else "moderate",
        "race_condition": "review_if_concurrent",
        "error_handling": "check",
        "security_impact": "elevated" if risk_score >= 61 else "low",
        "domain_invariants": "preserved" if not touches_frozen_invariant else "VIOLATED",
        "test_coverage": "ok" if has_tests else "INSUFFICIENT",
        "rollback_possible": "yes",
    }
    blockers: list[str] = []
    notes: list[str] = []

    for p in paths:
        if not path_allowed_for_auto_impl(p):
            blockers.append(f"path not allowlisted: {p}")
    if not has_tests:
        blockers.append("missing tests for change")
    if not measurable_benefit:
        blockers.append("no measurable improvement articulated")
    if touches_frozen_invariant:
        blockers.append("attempts to alter frozen production invariants")
    if risk_score >= 81:
        blockers.append("CRITICAL risk — auto-accept forbidden")

    if "safety" in diff_summary.lower() and any(inv in diff_summary for inv in FROZEN_PRODUCTION_INVARIANTS):
        blockers.append("diff references frozen invariant mutation")

    q["necessary"] = "yes" if measurable_benefit and not blockers else "no"
    approved = len(blockers) == 0
    if approved:
        notes.append("REVIEWER approve — IMPLEMENTER change may proceed to VERIFY")
    else:
        notes.append("REVIEWER reject")
    return ReviewResult(approved=approved, questions=q, blockers=blockers, notes=notes)
