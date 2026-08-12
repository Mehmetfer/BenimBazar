"""Self-Improving Autonomous Software Engine — inspect, improve, verify, rollback.

Can change its own *software quality*.
Cannot change production safety invariants, risk hard limits, kill switch,
credentials, auth, audit deletion, test deletion, or LIVE broker unlock.

Scores must be evidence-based; never claim 10.0 without proofs.
"""

from __future__ import annotations

from self_improvement.audit import Finding, Severity, audit_repository
from self_improvement.backlog import BacklogStore, ImprovementItem
from self_improvement.engine import SelfImprovementEngine, IterationReport
from self_improvement.invariants import FROZEN_PRODUCTION_INVARIANTS, SafetyViolation
from self_improvement.scorecard import SIScorecard, score_self_improvement

__all__ = [
    "BacklogStore",
    "Finding",
    "ImprovementItem",
    "IterationReport",
    "SIScorecard",
    "SafetyViolation",
    "SelfImprovementEngine",
    "Severity",
    "FROZEN_PRODUCTION_INVARIANTS",
    "audit_repository",
    "score_self_improvement",
]
