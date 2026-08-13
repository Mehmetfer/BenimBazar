"""Continuous controlled improvement loop with budgets + failure injection."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from autonomy.budget import AutonomyBudget, BudgetExceeded
from autonomy.components import (
    AuditLogger,
    Detector,
    Diagnoser,
    EvidenceCollector,
    LearningStore,
    Observer,
    Planner,
    ProposalEngine,
    RollbackManager,
    SandboxExecutor,
    TestRunner,
    VerificationEngine,
)
from autonomy.state_machine import AutonomyState, AutonomyStateMachine, InvalidTransition

FailureMode = Literal[
    "",
    "TEST_FAILURE",
    "BUILD_FAILURE",
    "VERIFICATION_FAILURE",
    "TIMEOUT",
    "RESOURCE_LIMIT",
]


@dataclass
class CycleReport:
    cycle_id: str
    observation: str = ""
    problem: str = ""
    evidence: list[str] = field(default_factory=list)
    diagnosis: str = ""
    proposal: str = ""
    files_changed: list[str] = field(default_factory=list)
    tests: str = ""
    verification: str = ""
    rollback: str = ""
    learning: str = ""
    next_proposal: str = ""
    state_history: list[str] = field(default_factory=list)
    final_state: str = ""
    production_mutated: bool = False
    auto_deployed: bool = False

    def write_markdown(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    f"# Autonomy Cycle `{self.cycle_id}`",
                    "",
                    f"Cycle: {self.cycle_id}",
                    f"Observation: {self.observation}",
                    f"Problem: {self.problem}",
                    f"Evidence: {'; '.join(self.evidence)}",
                    f"Diagnosis: {self.diagnosis}",
                    f"Proposal: {self.proposal}",
                    f"Files Changed: {', '.join(self.files_changed) or 'none'}",
                    f"Tests: {self.tests}",
                    f"Verification: {self.verification}",
                    f"Rollback: {self.rollback}",
                    f"Learning: {self.learning}",
                    f"Next Proposal: {self.next_proposal}",
                    f"Final State: {self.final_state}",
                    f"State History: {' → '.join(self.state_history)}",
                    "Production Mutated: false",
                    "Auto Deployed: false",
                    "LIVE Trading: false",
                    "",
                ]
            ),
            encoding="utf-8",
        )


class AutonomyLoop:
    def __init__(
        self,
        *,
        target_root: Path | None = None,
        budget: AutonomyBudget | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        pkg = Path(__file__).resolve().parents[1] / "self_verification" / "target"
        self.target_root = Path(target_root or pkg)
        self.budget = budget or AutonomyBudget()
        self.reports_dir = Path(reports_dir or "reports/autonomy")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.observer = Observer()
        self.evidence = EvidenceCollector()
        self.detector = Detector()
        self.diagnoser = Diagnoser()
        self.planner = Planner()
        self.proposals = ProposalEngine()
        self.tests = TestRunner()
        self.verify = VerificationEngine()
        self.learning = LearningStore(self.reports_dir / "learning.jsonl")
        self.audit = AuditLogger(self.reports_dir / "audit.jsonl")
        self.cycles: list[CycleReport] = []

    def run_cycle(self, *, inject: FailureMode = "") -> CycleReport:
        cycle_id = f"cycle_{uuid.uuid4().hex[:8]}"
        report = CycleReport(cycle_id=cycle_id)
        sm = AutonomyStateMachine()
        sandbox = SandboxExecutor(self.target_root)
        try:
            self.budget.begin_iteration()
        except BudgetExceeded as exc:
            sm.transition(AutonomyState.PAUSED_FOR_REVIEW)
            report.final_state = sm.state.value
            report.learning = f"budget_exceeded:{exc.reason}"
            report.state_history = list(sm.history)
            report.write_markdown(self.reports_dir / f"{cycle_id}.md")
            self.cycles.append(report)
            return report

        if inject == "RESOURCE_LIMIT":
            sm.transition(AutonomyState.PAUSED_FOR_REVIEW)
            report.observation = "resource_limit_injected"
            report.final_state = sm.state.value
            report.state_history = list(sm.history)
            report.learning = "PAUSED_FOR_REVIEW on resource limit"
            self.audit.write("RESOURCE_LIMIT", True, {"paused": True})
            report.write_markdown(self.reports_dir / f"{cycle_id}.md")
            self.cycles.append(report)
            return report

        if inject == "TIMEOUT":
            sm.transition(AutonomyState.ABORTED)
            report.observation = "timeout_injected"
            report.final_state = sm.state.value
            report.state_history = list(sm.history)
            report.learning = "ABORT on timeout"
            self.audit.write("TIMEOUT", False, {"aborted": True})
            report.write_markdown(self.reports_dir / f"{cycle_id}.md")
            self.cycles.append(report)
            return report

        try:
            sb = sandbox.enter()
            # OBSERVE
            observations = self.observer.observe_repo_markers(sb)
            report.observation = "; ".join(o.message for o in observations)
            self.audit.write("OBSERVE", True, {"n": len(observations)})
            # stay OBSERVING until detect
            ev = self.evidence.collect(observations)
            report.evidence = list(ev.items)[:12]
            problem = self.detector.detect(observations)
            if problem is None:
                report.problem = "none"
                report.final_state = sm.state.value
                report.state_history = list(sm.history)
                report.next_proposal = "scan_for_todo_fixme_or_coverage_gaps"
                report.write_markdown(self.reports_dir / f"{cycle_id}.md")
                self.cycles.append(report)
                return report

            sm.transition(AutonomyState.DETECTED)
            report.problem = problem.message
            sm.transition(AutonomyState.DIAGNOSING)
            diagnosis = self.diagnoser.diagnose(problem, ev)
            report.diagnosis = diagnosis.root_cause
            sm.transition(AutonomyState.PLANNING)
            plan = self.planner.plan(problem, diagnosis)
            self.audit.write("PLAN", True, plan)

            broken = (sb / "module.py").read_text(encoding="utf-8") if (sb / "module.py").is_file() else ""
            proposal = self.proposals.propose(problem, diagnosis, broken_source=broken)
            report.proposal = proposal.proposal_id
            if self.learning.should_block(proposal.problem, proposal.plan):
                sm.transition(AutonomyState.PROPOSED)
                sm.transition(AutonomyState.PAUSED_FOR_REVIEW)
                report.learning = "blocked_repeat_failed_proposal"
                report.final_state = sm.state.value
                report.state_history = list(sm.history)
                report.write_markdown(self.reports_dir / f"{cycle_id}.md")
                self.cycles.append(report)
                return report

            sm.transition(AutonomyState.PROPOSED)
            sm.transition(AutonomyState.SANDBOXING)
            if inject == "BUILD_FAILURE":
                # corrupt patch intentionally
                proposal.patch_files["module.py"] = "def oops(:\n"
            changed = sandbox.apply(proposal)
            self.budget.record_files(len(changed))
            report.files_changed = changed
            rb = RollbackManager(sandbox)

            sm.transition(AutonomyState.TESTING)
            t0 = time.time()
            if inject == "TEST_FAILURE":
                ok, out = False, "injected_test_failure"
            else:
                ok, out = self.tests.run_sandbox_assert(sb)
            self.budget.record_test_runtime(time.time() - t0)
            report.tests = f"{'PASS' if ok else 'FAIL'}: {out}"

            sm.transition(AutonomyState.VERIFYING)
            if inject == "VERIFICATION_FAILURE":
                verified, vmsg = False, "injected_verification_failure"
            else:
                verified, vmsg = self.verify.verify(sb, ok)
            report.verification = f"{'PASS' if verified else 'FAIL'}: {vmsg}"

            if ok and verified:
                sm.transition(AutonomyState.PASSED)
                sm.transition(AutonomyState.READY_FOR_REVIEW)
                report.learning = "proposal_ready_for_human_review"
                report.next_proposal = "improve_test_coverage_adjacent_module"
                self.learning.record(
                    {
                        "fingerprint": f"{proposal.problem}::{proposal.plan}".lower(),
                        "result": "PASSED",
                        "proposal": proposal.to_dict(),
                    }
                )
            else:
                sm.transition(AutonomyState.FAILED)
                try:
                    self.budget.record_failure()
                except BudgetExceeded:
                    pass
                sm.transition(AutonomyState.ROLLING_BACK)
                restored = rb.rollback()
                report.rollback = f"restored:{','.join(restored)}"
                # confirm baseline broken restored for defect fixture
                post = (sb / "module.py").read_text(encoding="utf-8")
                assert "BROKEN" in post or "intentional defect" in post or inject == "BUILD_FAILURE"
                sm.transition(AutonomyState.LEARNED)
                lesson = "Do not retry identical failing proposal without new evidence"
                report.learning = lesson
                self.learning.record(
                    {
                        "fingerprint": f"{proposal.problem}::{proposal.plan}".lower(),
                        "result": "FAILED",
                        "failure": report.tests,
                        "rollback": report.rollback,
                        "lesson": lesson,
                        "proposal": proposal.to_dict(),
                    }
                )
                report.next_proposal = "revise_patch_with_stronger_tests"
        except BudgetExceeded as exc:
            try:
                sm.transition(AutonomyState.PAUSED_FOR_REVIEW)
            except InvalidTransition:
                pass
            report.learning = f"budget:{exc.reason}"
        except Exception as exc:  # noqa: BLE001
            report.learning = f"error:{exc}"
            try:
                sandbox.rollback()
                report.rollback = "emergency_rollback"
            except Exception:  # noqa: BLE001
                pass
        finally:
            report.state_history = list(sm.history)
            report.final_state = sm.state.value
            report.production_mutated = False
            report.auto_deployed = False
            report.write_markdown(self.reports_dir / f"{cycle_id}.md")
            self.cycles.append(report)
            sandbox.close()
        return report

    def run_until_budget(self, *, max_cycles: int | None = None) -> list[CycleReport]:
        """while improvement_budget_available — controlled continuous loop."""
        out: list[CycleReport] = []
        limit = max_cycles if max_cycles is not None else self.budget.max_iterations
        for _ in range(limit):
            if self.budget.remaining_iterations() <= 0:
                break
            try:
                self.budget.check()
            except BudgetExceeded:
                break
            out.append(self.run_cycle())
            if out[-1].final_state == AutonomyState.PAUSED_FOR_REVIEW.value:
                break
        return out
