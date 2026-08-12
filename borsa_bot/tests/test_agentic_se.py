"""Unit tests for Autonomous Software Engineering agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_se.benchmarks import (
    bench_file_discovery,
    bench_quality_gate,
    bench_refuse_weaken_assertion,
    bench_repo_understanding,
    bench_task_decomposition,
    run_all_benchmarks,
)
from agentic_se.boundaries import SafetyViolation, assert_se_writes_safe
from agentic_se.checkpoint import CheckpointStore
from agentic_se.engine import AutonomousSoftwareEngine
from agentic_se.quality import evaluate_quality
from agentic_se.repair import repair_loop
from agentic_se.scorecard import score_software_engineering_autonomy


def test_boundaries_block_live_and_kill():
    with pytest.raises(SafetyViolation):
        assert_se_writes_safe({"agentic_se/x.py": "live_broker_enabled=True"})
    with pytest.raises(SafetyViolation):
        assert_se_writes_safe({"risk/engine.py": "x=1"})


def test_checkpoint_restore(tmp_path: Path):
    root = tmp_path
    (root / "agentic_se").mkdir()
    f = root / "agentic_se" / "a.py"
    f.write_text("A\n", encoding="utf-8")
    store = CheckpointStore(root)
    store.save("base", ["agentic_se/a.py"])
    f.write_text("B\n", encoding="utf-8")
    store.restore()
    assert f.read_text(encoding="utf-8") == "A\n"


def test_repair_max_iterations():
    def apply_patch(failure: str, idx: int) -> tuple[bool, str, str]:
        return True, f"p{idx}", "fail"

    def retest() -> tuple[bool, str]:
        return False, "fail"

    res = repair_loop(
        failure_excerpt="AssertionError",
        test_node="t",
        apply_patch=apply_patch,
        retest=retest,
        max_iterations=2,
    )
    assert res.exhausted and not res.ok
    assert len(res.attempts) == 2


def test_quality_gate_requires_all():
    q = evaluate_quality(
        requirements_satisfied=True,
        implementation_complete=True,
        tests_added_when_needed=True,
        existing_tests_pass=True,
        new_tests_pass=False,
        typecheck_pass=True,
        regression_pass=True,
        security_reviewed=True,
        domain_invariants_ok=True,
        git_diff_reviewed=True,
        no_destructive_unrelated=True,
    )
    assert q.ok is False


def test_plan_only_goal():
    eng = AutonomousSoftwareEngine()
    rep = eng.run_goal("Document agentic_se loop stages")
    assert rep.waited_for_human is False
    assert rep.status == "DELIVERED"
    assert "TASK_DECOMPOSITION" in rep.stages


def test_core_benches():
    assert bench_repo_understanding().success
    assert bench_task_decomposition().success
    assert bench_file_discovery().success
    assert bench_refuse_weaken_assertion().success
    assert bench_quality_gate().success


def test_scorecard_caps_below_10():
    sc = score_software_engineering_autonomy(
        bench={
            "repository_understanding": True,
            "task_decomposition": True,
            "bug_fix_tdd": True,
            "missing_test": True,
            "debugging_recovery": True,
            "refuse_assertion_weakening": True,
            "quality_gate": True,
            "autonomous_file_discovery": True,
            "long_run_stages": True,
            "orchestrator_e2e": True,
        },
        benchmark_passed=10,
        benchmark_total=10,
    )
    assert sc.software_engineering_autonomy <= 9.4
    assert sc.live_money_autonomy == "NOT VERIFIED"
    assert sc.full_level8_claimed is False


def test_full_benchmark_suite():
    payload = run_all_benchmarks()
    assert payload["passed"] == payload["total"], payload
