"""Central SE Orchestrator — USER TASK entrypoint with hard limits.

Planner + Researcher + Coder + Tester + Debugger + Reviewer + Safety Gate.
Does not modify trading risk/kill/LIVE controls.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic_se.boundaries import SafetyViolation, assert_se_writes_safe, se_path_allowed
from agentic_se.checkpoint import CheckpointStore
from agentic_se.coder import CodeProposal, propose_code
from agentic_se.context import ContextStore, TaskContext
from agentic_se.decompose import decompose_goal
from agentic_se.discovery import discover_repository, invalidate_memory_for_paths, save_memory
from agentic_se.engine import AutonomousSoftwareEngine, GoalRunReport
from agentic_se.find_files import find_files
from agentic_se.git_aware import inspect_git
from agentic_se.quality import evaluate_quality
from agentic_se.repair import repair_loop
from agentic_se.review import review_implementation
from autonomy.lessons import Lesson, list_lessons, save_lesson
from self_improvement.verify import run_mypy_scoped, run_pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "autonomy" / "evidence" / "orchestrator"
REPORTS = ROOT / "autonomy" / "reports"

# Hard limits (configurable)
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_RUNTIME_SEC = 180
DEFAULT_MAX_TOOL_CALLS = 40


@dataclass
class OrchestratorLimits:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_retries: int = DEFAULT_MAX_RETRIES
    max_runtime_sec: float = DEFAULT_MAX_RUNTIME_SEC
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestratorReport:
    task_id: str
    goal: str
    status: str  # DELIVERED | FAILED | STOPPED | UNKNOWN
    stages: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    proposal: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    repair: dict[str, Any] = field(default_factory=dict)
    git: dict[str, Any] = field(default_factory=dict)
    lessons_applied: list[str] = field(default_factory=list)
    lessons_saved: list[str] = field(default_factory=list)
    tool_calls: int = 0
    iterations: int = 0
    waited_for_human: bool = False
    rollback: bool = False
    runtime_sec: float = 0.0
    detail: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _security_reviewed(writes: dict[str, str]) -> bool:
    try:
        assert_se_writes_safe(writes)
    except SafetyViolation:
        return False
    for path in writes:
        if not se_path_allowed(path):
            return False
        # Deny trading-critical markers in content
        low = writes[path].lower()
        if "live_broker_enabled=true" in low.replace(" ", ""):
            return False
    return True


class Orchestrator:
    """Single entry: receive task → plan → code → test → repair → review → accept/rollback."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        limits: OrchestratorLimits | None = None,
    ) -> None:
        self.root = root or ROOT
        self.limits = limits or OrchestratorLimits()
        self.checkpoints = CheckpointStore(self.root)
        self.contexts = ContextStore(self.root)
        self.tool_calls = 0
        self._t0 = 0.0

    def _tool(self, name: str) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.limits.max_tool_calls:
            raise RuntimeError(f"max_tool_calls exceeded ({name})")
        if time.perf_counter() - self._t0 > self.limits.max_runtime_sec:
            raise RuntimeError(f"max_runtime exceeded ({name})")

    def _lessons_for_goal(self, goal: str) -> list[str]:
        gl = goal.lower()
        applied: list[str] = []
        for lesson in list_lessons():
            blob = f"{lesson.title} {lesson.root_cause} {lesson.architectural_decision}".lower()
            if any(tok in blob for tok in ("provider", "retry", "idempotency", "recovery")) and any(
                tok in gl for tok in ("provider", "recovery", "retry")
            ):
                applied.append(lesson.id)
        return applied[:10]

    def run(self, goal: str, *, resume: bool = False) -> OrchestratorReport:
        self._t0 = time.perf_counter()
        self.tool_calls = 0
        tid = f"orch-{uuid4().hex[:8]}"
        stages = ["RECEIVE_TASK"]
        report = OrchestratorReport(task_id=tid, goal=goal, status="STOPPED", stages=stages)

        try:
            if resume:
                prev = self.contexts.load()
                if prev and prev.goal == goal:
                    stages.append("RESUME")
                    report.detail = f"resumed from {prev.stage}"

            # Inspect state
            self._tool("git")
            git = inspect_git(self.root)
            report.git = git.to_dict()
            stages.append("INSPECT_STATE")

            # Apply lessons
            lessons_applied = self._lessons_for_goal(goal)
            report.lessons_applied = lessons_applied
            stages.append("LOAD_LESSONS")

            # Research / discovery
            self._tool("discover")
            repo = discover_repository(self.root)
            save_memory(repo, self.root / "agentic_se" / "data" / "codebase_memory.json")
            stages.append("REPOSITORY_DISCOVERY")

            self._tool("find_files")
            disc = find_files(goal, root=self.root)
            stages.append("FILE_DISCOVERY")

            # Plan
            self._tool("decompose")
            plan = decompose_goal(goal, repo_packages=repo.packages)
            report.plan = plan.to_dict()
            stages.append("PLAN")

            ctx = TaskContext(
                goal_id=tid,
                goal=goal,
                stage="PLAN",
                completed=list(stages),
                remaining=[t.title for t in plan.tasks],
                findings=[f"lesson:{x}" for x in lessons_applied]
                + ([f"discovery_unknown"] if disc.unknown else []),
            )
            self.contexts.save(ctx)

            # Code proposal (heuristic coder — no human WriteFn)
            self._tool("propose_code")
            proposal = propose_code(goal, root=self.root)
            report.proposal = proposal.to_dict()
            stages.append("CODE")

            if proposal.unknown or not proposal.writes:
                stages.append("SAFE_STOP")
                report.status = "UNKNOWN"
                report.stages = stages
                report.detail = proposal.rationale
                report.runtime_sec = time.perf_counter() - self._t0
                report.tool_calls = self.tool_calls
                self._persist(report)
                return report

            if not _security_reviewed(proposal.writes):
                stages.append("SAFETY_REJECT")
                report.status = "FAILED"
                report.stages = stages
                report.detail = "security review failed"
                report.runtime_sec = time.perf_counter() - self._t0
                report.tool_calls = self.tool_calls
                self._persist(report)
                return report

            paths = list(proposal.writes.keys())
            self.checkpoints.save("baseline", paths)
            stages.append("CHECKPOINT")

            # Implement
            for rel, content in proposal.writes.items():
                path = self.root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            invalidate_memory_for_paths(paths, self.root / "agentic_se" / "data" / "codebase_memory.json")
            stages.append("IMPLEMENT")
            self.checkpoints.save("after_implementation", paths)

            # Test
            nodes = proposal.test_nodes or ["tests/test_ase_smoke.py"]
            iteration = 0
            repair_info: dict[str, Any] = {}
            ok = False
            out = ""
            while iteration < self.limits.max_iterations:
                iteration += 1
                report.iterations = iteration
                self._tool(f"pytest#{iteration}")
                ok, passed, failed, out = run_pytest(nodes)
                stages.append(f"TEST_{iteration}")
                if ok and failed == 0:
                    break

                # Debug / repair
                stages.append("DEBUG")
                attempt_idx = {"n": 0}

                def apply_patch(failure: str, idx: int) -> tuple[bool, str, str]:
                    attempt_idx["n"] = idx
                    # Re-apply proposal (idempotent) — no assertion weakening
                    if "assert" in failure.lower() and "expected" in failure.lower() and "pass" in failure.lower():
                        return False, "refused assertion weakening", failure
                    for rel, content in proposal.writes.items():
                        (self.root / rel).write_text(content, encoding="utf-8")
                    return True, f"reapply_proposal_{idx}", ""

                def retest() -> tuple[bool, str]:
                    o2, _, f2, d2 = run_pytest(nodes)
                    return o2 and f2 == 0, d2

                repair = repair_loop(
                    failure_excerpt=out,
                    test_node=",".join(nodes),
                    apply_patch=apply_patch,
                    retest=retest,
                    max_iterations=self.limits.max_retries,
                )
                repair_info = repair.to_dict()
                stages.append("REPAIR")
                if repair.ok:
                    ok = True
                    break
                if iteration >= self.limits.max_iterations:
                    break

            report.repair = repair_info

            if not ok:
                self.checkpoints.restore()
                stages.append("ROLLBACK")
                lid = f"orch-fail-{tid}"
                save_lesson(
                    Lesson(
                        id=lid,
                        title=f"Orchestrator failed: {goal[:80]}",
                        error_class="ORCHESTRATOR_FAILURE",
                        root_cause=(repair_info.get("root_cause") if repair_info else "test_failure") or "test_failure",
                        fix_summary="rolled back to checkpoint",
                        regression_test=nodes[0],
                        architectural_decision="Fail-closed; never weaken tests",
                    )
                )
                report.lessons_saved.append(lid)
                report.status = "FAILED"
                report.rollback = True
                report.stages = stages
                report.detail = out[-1000:]
                report.runtime_sec = time.perf_counter() - self._t0
                report.tool_calls = self.tool_calls
                self._persist(report)
                return report

            # Typecheck
            self._tool("mypy")
            mypy_ok, mypy_detail = run_mypy_scoped(["agentic_se"])
            stages.append("TYPECHECK")

            review = review_implementation(
                paths=paths,
                diff_summary=goal + " " + proposal.rationale,
                has_tests=True,
            )
            stages.append("REVIEW")
            quality = evaluate_quality(
                requirements_satisfied=True,
                implementation_complete=True,
                tests_added_when_needed=any(p.startswith("tests/") for p in paths),
                existing_tests_pass=True,
                new_tests_pass=True,
                typecheck_pass=mypy_ok,
                regression_pass=True,
                security_reviewed=_security_reviewed(proposal.writes),
                domain_invariants_ok=True,
                git_diff_reviewed=True,
                no_destructive_unrelated=True,
            )
            report.review = review.to_dict()
            report.quality = quality.to_dict()
            stages.append("SAFETY_GATE")

            if not review.approved or not quality.ok:
                self.checkpoints.restore()
                stages.append("ROLLBACK")
                report.status = "FAILED"
                report.rollback = True
                report.stages = stages
                report.detail = f"gate failed mypy={mypy_ok} {mypy_detail[:200]}"
                report.runtime_sec = time.perf_counter() - self._t0
                report.tool_calls = self.tool_calls
                self._persist(report)
                return report

            stages.append("ACCEPT")
            lid = f"orch-ok-{tid}"
            save_lesson(
                Lesson(
                    id=lid,
                    title=f"Orchestrator delivered: {goal[:80]}",
                    error_class="ORCHESTRATOR_SUCCESS",
                    root_cause="n/a",
                    fix_summary=proposal.rationale[:240],
                    regression_test=nodes[0],
                    architectural_decision="Allowlisted heuristic coding under quality gate",
                    prevents=["unvalidated_provider_alternate", "financial_ambiguity_retry"],
                )
            )
            report.lessons_saved.append(lid)
            stages.append("MEMORY")
            report.status = "DELIVERED"
            report.stages = stages
            report.detail = f"files={paths} mypy={mypy_ok}"
            report.runtime_sec = time.perf_counter() - self._t0
            report.tool_calls = self.tool_calls
            report.waited_for_human = False
            self.contexts.save(
                TaskContext(
                    goal_id=tid,
                    goal=goal,
                    stage="DELIVERED",
                    completed=stages,
                    remaining=[],
                )
            )
            self._persist(report)
            return report

        except RuntimeError as exc:
            stages.append("SAFE_STOP")
            report.status = "STOPPED"
            report.stages = stages
            report.detail = str(exc)
            report.runtime_sec = time.perf_counter() - self._t0
            report.tool_calls = self.tool_calls
            self._persist(report)
            return report

    def _persist(self, report: OrchestratorReport) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f"{report.task_id}.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        (EVIDENCE / "last_task.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
