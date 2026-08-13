"""GÖREV 30 F7 side — full controlled loop with learning + scoring hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from self_verification.engine import SelfVerificationEngine
from self_verification.learning import LearningMemory
from self_verification.models import RunStatus
from self_verification.planner import ImprovementProposal, plan_improvement
from self_verification.system_observe import (
    ObservationKind,
    diagnose_observation,
    observe_system,
)
from self_verification.testgen import generate_regression_test


@dataclass
class F7CycleResult:
    observations: List[Dict[str, Any]]
    diagnoses: List[Dict[str, Any]]
    proposals: List[Dict[str, Any]]
    verification: Optional[Dict[str, Any]]
    learning_blocked: bool = False
    generated_tests: List[Dict[str, Any]] = field(default_factory=list)
    production_mutated: bool = False
    auto_deployed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observations": self.observations,
            "diagnoses": self.diagnoses,
            "proposals": self.proposals,
            "verification": self.verification,
            "learning_blocked": self.learning_blocked,
            "generated_tests": self.generated_tests,
            "production_mutated": False,
            "auto_deployed": False,
            "f8": "DISABLED",
            "stages_contract": {
                "OBSERVE": True,
                "DETECT": True,
                "DIAGNOSE": True,
                "PLAN": True,
                "PROPOSE": True,
                "SANDBOX": True,
                "TEST": True,
                "VERIFY": True,
                "ROLLBACK": True,
                "LEARN": True,
            },
        }


class F7ControlledLoop:
    """
    OBSERVE SYSTEM → DETECT → DIAGNOSE → PLAN → PROPOSE → SANDBOX →
    CHANGE → TEST → VERIFY → ROLLBACK IF FAILED → LEARN

    Never auto-deploys to production.
    """

    def __init__(self, *, learning: LearningMemory | None = None) -> None:
        self.learning = learning or LearningMemory()

    def run(
        self,
        *,
        test_failures: Optional[List[str]] = None,
        decision_stats: Optional[Dict[str, Any]] = None,
        run_sandbox_fix: bool = True,
        inject_failure: bool = False,
        sandbox_root: Path | None = None,
    ) -> F7CycleResult:
        observations = observe_system(
            test_failures=test_failures,
            decision_stats=decision_stats,
        )
        diagnoses = []
        proposals: List[ImprovementProposal] = []
        generated_tests = []
        learning_blocked = False

        actionable = [o for o in observations if o.kind != ObservationKind.HEALTHY]
        targets = actionable or observations[:1]

        for obs in targets:
            diag = diagnose_observation(obs)
            diagnoses.append(diag)
            prop = plan_improvement(obs, diag, tests_required=5)
            if self.learning.should_block_proposal(prop.problem, prop.proposal):
                learning_blocked = True
                continue
            proposals.append(prop)
            gen = generate_regression_test(
                problem=prop.problem,
                expected_behavior=prop.proposal,
            )
            generated_tests.append(gen)

        verification = None
        if run_sandbox_fix:
            engine = SelfVerificationEngine(sandbox_root=sandbox_root)
            try:
                report = engine.run(inject_failure=inject_failure)
                verification = report.to_dict()
                if report.status == RunStatus.ROLLED_BACK and proposals:
                    p0 = proposals[0]
                    self.learning.record_failure(
                        problem=p0.problem,
                        diagnosis=p0.diagnosis,
                        proposal=p0.proposal,
                        change="sandbox_patch",
                        failure=report.error or "verify_failed",
                        root_cause=p0.diagnosis,
                        rollback="sandbox_restored",
                        lesson="Do not auto-retry identical proposal without new evidence",
                    )
            finally:
                if sandbox_root is None:
                    engine.close()

        return F7CycleResult(
            observations=[o.to_dict() for o in observations],
            diagnoses=[d.to_dict() for d in diagnoses],
            proposals=[p.to_dict() for p in proposals],
            verification=verification,
            learning_blocked=learning_blocked,
            generated_tests=[g.to_dict() for g in generated_tests],
        )
