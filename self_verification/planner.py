"""GÖREV 23 + 29 — Controlled planner + improvement scoring (no production mutate)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from self_verification.system_observe import RootCauseDiagnosis, SystemObservation


@dataclass
class ImprovementProposal:
    proposal_id: str
    problem: str
    diagnosis: str
    proposal: str
    risk: str
    tests_required: int
    rollback: str
    expected_benefit: float
    confidence: float
    test_coverage: float
    rollback_available: bool
    complexity: float
    score: float
    evidence: List[str] = field(default_factory=list)
    applies_to_production: bool = False
    auto_apply: bool = False
    requires_human_approval: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "problem": self.problem,
            "diagnosis": self.diagnosis,
            "proposal": self.proposal,
            "risk": self.risk,
            "tests_required": self.tests_required,
            "rollback": self.rollback,
            "expected_benefit": self.expected_benefit,
            "confidence": self.confidence,
            "test_coverage": self.test_coverage,
            "rollback_available": self.rollback_available,
            "complexity": self.complexity,
            "improvement_score": self.score,
            "evidence": list(self.evidence),
            "applies_to_production": False,
            "auto_apply": False,
            "requires_human_approval": True,
            "score_alone_does_not_authorize_apply": True,
            "created_at": self.created_at,
        }


def score_improvement(
    *,
    expected_benefit: float,
    risk: str,
    confidence: float,
    test_coverage: float,
    rollback_available: bool,
    complexity: float,
) -> float:
    risk_penalty = {"low": 0.0, "medium": 0.15, "high": 0.35, "critical": 0.55}.get(risk.lower(), 0.2)
    rollback_bonus = 0.1 if rollback_available else -0.2
    raw = (
        0.35 * expected_benefit
        + 0.25 * confidence
        + 0.2 * test_coverage
        + rollback_bonus
        - 0.15 * complexity
        - risk_penalty
    )
    return round(max(0.0, min(1.0, raw)), 4)


def plan_improvement(
    observation: SystemObservation,
    diagnosis: RootCauseDiagnosis,
    *,
    tests_required: int = 3,
) -> ImprovementProposal:
    """Observation + Diagnosis + Evidence → ImprovementProposal (sandbox path only)."""
    risk = "high" if observation.severity in ("high", "critical") else "medium"
    if diagnosis.category == "NONE":
        risk = "low"
    expected_benefit = 0.7 if diagnosis.category in ("TEST", "UI", "DATA") else 0.5
    complexity = 0.4 if diagnosis.category in ("TEST", "CONFIG") else 0.6
    test_coverage = min(1.0, tests_required / 5.0)
    conf = diagnosis.confidence
    sc = score_improvement(
        expected_benefit=expected_benefit,
        risk=risk,
        confidence=conf,
        test_coverage=test_coverage,
        rollback_available=True,
        complexity=complexity,
    )
    return ImprovementProposal(
        proposal_id=f"imp-{uuid.uuid4().hex[:10]}",
        problem=observation.message,
        diagnosis=diagnosis.root_cause,
        proposal=diagnosis.suggested_fix,
        risk=risk,
        tests_required=tests_required,
        rollback="Available — restore sandbox baseline snapshot",
        expected_benefit=expected_benefit,
        confidence=conf,
        test_coverage=test_coverage,
        rollback_available=True,
        complexity=complexity,
        score=sc,
        evidence=list(diagnosis.evidence),
    )
