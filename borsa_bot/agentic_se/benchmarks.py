"""ASE benchmark suite — scores must come from these results, not vibes."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agentic_se.checkpoint import CheckpointStore
from agentic_se.decompose import decompose_goal
from agentic_se.discovery import discover_repository, load_memory, save_memory
from agentic_se.engine import AutonomousSoftwareEngine
from agentic_se.find_files import find_files
from agentic_se.quality import evaluate_quality
from agentic_se.repair import repair_loop
from agentic_se.review import review_implementation
from self_improvement.verify import run_pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "autonomy" / "evidence" / "agentic_se"


@dataclass
class BenchResult:
    name: str
    category: str  # coding|recovery|reasoning
    success: bool
    seconds: float
    iterations: int = 0
    tests_run: int = 0
    regressions: int = 0
    rollbacks: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _time_call(fn: Callable[[], BenchResult]) -> BenchResult:
    t0 = time.perf_counter()
    res = fn()
    res.seconds = time.perf_counter() - t0
    return res


def bench_repo_understanding() -> BenchResult:
    def run() -> BenchResult:
        repo = discover_repository(ROOT)
        save_memory(repo)
        mem = load_memory()
        ok = bool(mem and repo.packages and "agentic_se" in " ".join(repo.packages))
        return BenchResult(
            "repository_understanding",
            "reasoning",
            ok,
            0.0,
            detail=f"packages={len(repo.packages)} modules={len(repo.modules)}",
        )

    return _time_call(run)


def bench_task_decomposition() -> BenchResult:
    def run() -> BenchResult:
        plan = decompose_goal("Improve agentic_se memory invalidation and benchmarks")
        ok = len(plan.tasks) >= 4 and bool(plan.acceptance) and bool(plan.requirements)
        return BenchResult("task_decomposition", "reasoning", ok, 0.0, detail=f"tasks={len(plan.tasks)}")

    return _time_call(run)


def bench_file_discovery() -> BenchResult:
    def run() -> BenchResult:
        d = find_files("AutonomousSoftwareEngine quality gate")
        ok = any("agentic_se" in h for h in d.code_hits) or any("agentic_se" in h for h in d.test_hits)
        return BenchResult("autonomous_file_discovery", "reasoning", ok, 0.0, detail=str(d.to_dict())[:300])

    return _time_call(run)


def bench_bugfix_tdd() -> BenchResult:
    """Inject bug → write reproduction test → fix → retest."""

    def run() -> BenchResult:
        eng = AutonomousSoftwareEngine()
        playground = ROOT / "agentic_se" / "playground.py"
        test_path = ROOT / "tests" / "test_ase_playground.py"
        original = playground.read_text(encoding="utf-8")
        cp = CheckpointStore()
        cp.save("bench_bug_baseline", ["agentic_se/playground.py", "tests/test_ase_playground.py"])

        # 1) Inject bug
        buggy = original.replace("return a + b", "return a - b  # BENCH_BUG")
        playground.write_text(buggy, encoding="utf-8")

        # 2) Reproduction test (TDD)
        test_path.write_text(
            'from agentic_se.playground import buggy_add\n\ndef test_buggy_add_sum():\n    assert buggy_add(2, 3) == 5\n',
            encoding="utf-8",
        )
        ok_fail, _, failed, _ = run_pytest(["tests/test_ase_playground.py"])
        repro_ok = (not ok_fail) or failed > 0  # must fail under bug

        # 3) Fix via engine implement callback
        def implement() -> dict[str, str]:
            return {
                "agentic_se/playground.py": original,  # restore correct impl
                "tests/test_ase_playground.py": test_path.read_text(encoding="utf-8"),
            }

        rep = eng.run_goal(
            "Fix buggy_add regression with reproduction test",
            implement=implement,
            test_nodes=["tests/test_ase_playground.py", "tests/test_ase_smoke.py"],
            require_new_tests=True,
        )
        success = repro_ok and rep.status == "DELIVERED"
        # ensure fixed
        ok2, passed, failed2, _ = run_pytest(["tests/test_ase_playground.py"])
        success = success and ok2 and failed2 == 0
        return BenchResult(
            "bug_fix_tdd",
            "coding",
            success,
            0.0,
            iterations=1,
            tests_run=passed,
            regressions=0,
            rollbacks=1 if rep.rollback else 0,
            detail=f"repro_failed={repro_ok} deliver={rep.status}",
        )

    return _time_call(run)


def bench_missing_test() -> BenchResult:
    def run() -> BenchResult:
        test_path = ROOT / "tests" / "test_ase_clamp.py"
        content = (
            "from agentic_se.playground import clamp_non_negative\n\n"
            "def test_clamp_negative():\n"
            "    assert clamp_non_negative(-3) == 0\n\n"
            "def test_clamp_positive():\n"
            "    assert clamp_non_negative(4) == 4\n"
        )

        eng = AutonomousSoftwareEngine()

        def implement() -> dict[str, str]:
            return {"tests/test_ase_clamp.py": content}

        rep = eng.run_goal(
            "Add missing tests for clamp_non_negative",
            implement=implement,
            test_nodes=["tests/test_ase_clamp.py"],
            require_new_tests=True,
        )
        ok, passed, failed, _ = run_pytest(["tests/test_ase_clamp.py"])
        return BenchResult(
            "missing_test",
            "coding",
            rep.status == "DELIVERED" and ok and failed == 0,
            0.0,
            tests_run=passed,
            detail=rep.status,
        )

    return _time_call(run)


def bench_recovery_and_rollback() -> BenchResult:
    def run() -> BenchResult:
        calls = {"n": 0}

        def apply_patch(failure: str, idx: int) -> tuple[bool, str, str]:
            calls["n"] += 1
            if idx < 2:
                return True, f"attempt-{idx}", "still failing"
            return True, "final", ""

        def retest() -> tuple[bool, str]:
            # fail twice then pass
            if calls["n"] < 3:
                return False, "still failing"
            return True, "ok"

        res = repair_loop(
            failure_excerpt="AssertionError: expected 5",
            test_node="tests/test_ase_playground.py",
            apply_patch=apply_patch,
            retest=retest,
            max_iterations=3,
        )
        return BenchResult(
            "debugging_recovery",
            "recovery",
            res.ok and len(res.attempts) >= 2,
            0.0,
            iterations=len(res.attempts),
            detail=res.root_cause,
        )

    return _time_call(run)


def bench_refuse_weaken_assertion() -> BenchResult:
    def run() -> BenchResult:
        review = review_implementation(
            paths=["tests/test_ase_playground.py"],
            diff_summary="weaken assertion to pass",
            has_tests=True,
            weakened_assertions=True,
        )
        return BenchResult(
            "refuse_assertion_weakening",
            "recovery",
            review.approved is False,
            0.0,
            detail=";".join(review.blockers),
        )

    return _time_call(run)


def bench_quality_gate() -> BenchResult:
    def run() -> BenchResult:
        bad = evaluate_quality(
            requirements_satisfied=True,
            implementation_complete=True,
            tests_added_when_needed=False,
            existing_tests_pass=True,
            new_tests_pass=True,
            typecheck_pass=True,
            regression_pass=True,
            security_reviewed=True,
            domain_invariants_ok=True,
            git_diff_reviewed=True,
            no_destructive_unrelated=True,
        )
        good = evaluate_quality(
            requirements_satisfied=True,
            implementation_complete=True,
            tests_added_when_needed=True,
            existing_tests_pass=True,
            new_tests_pass=True,
            typecheck_pass=True,
            regression_pass=True,
            security_reviewed=True,
            domain_invariants_ok=True,
            git_diff_reviewed=True,
            no_destructive_unrelated=True,
        )
        return BenchResult(
            "quality_gate",
            "reasoning",
            (not bad.ok) and good.ok,
            0.0,
            detail=f"bad={bad.ok} good={good.ok}",
        )

    return _time_call(run)


def bench_long_run_stages() -> BenchResult:
    def run() -> BenchResult:
        eng = AutonomousSoftwareEngine()
        rep = eng.run_goal("Map agentic_se package structure")  # plan-only
        required = {"USER_GOAL", "UNDERSTAND", "REPOSITORY_DISCOVERY", "TASK_DECOMPOSITION", "PLAN", "FILE_DISCOVERY"}
        ok = required.issubset(set(rep.stages)) and rep.status == "DELIVERED"
        return BenchResult(
            "long_run_stages",
            "reasoning",
            ok,
            0.0,
            detail=",".join(rep.stages),
        )

    return _time_call(run)


def bench_orchestrator_e2e() -> BenchResult:
    def run() -> BenchResult:
        from agentic_se.orchestrator import Orchestrator, OrchestratorLimits

        orch = Orchestrator(limits=OrchestratorLimits(max_iterations=2, max_retries=2))
        rep = orch.run("Provider recovery sistemini geliştir")
        ok = rep.status == "DELIVERED" and "IMPLEMENT" in rep.stages and not rep.waited_for_human
        return BenchResult(
            "orchestrator_e2e",
            "coding",
            ok,
            0.0,
            iterations=rep.iterations,
            rollbacks=1 if rep.rollback else 0,
            detail=f"{rep.status} tools={rep.tool_calls}",
        )

    return _time_call(run)


def run_all_benchmarks() -> dict[str, Any]:
    benches = [
        bench_repo_understanding,
        bench_task_decomposition,
        bench_file_discovery,
        bench_bugfix_tdd,
        bench_missing_test,
        bench_recovery_and_rollback,
        bench_refuse_weaken_assertion,
        bench_quality_gate,
        bench_long_run_stages,
        bench_orchestrator_e2e,
    ]
    results = [b() for b in benches]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [r.to_dict() for r in results],
        "passed": sum(1 for r in results if r.success),
        "total": len(results),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "benchmarks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
