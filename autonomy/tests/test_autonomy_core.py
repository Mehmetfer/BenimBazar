"""Autonomy core unit + failure-injection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from autonomy.budget import AutonomyBudget, BudgetExceeded
from autonomy.loop import AutonomyLoop
from autonomy.state_machine import AutonomyState, AutonomyStateMachine, InvalidTransition

TARGET = Path(__file__).resolve().parents[2] / "self_verification" / "target"


def test_state_machine_forbids_observing_to_ready_directly():
    sm = AutonomyStateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition(AutonomyState.READY_FOR_REVIEW)


def test_happy_path_ready_for_review(tmp_path):
    loop = AutonomyLoop(target_root=TARGET, budget=AutonomyBudget(max_iterations=3), reports_dir=tmp_path)
    report = loop.run_cycle()
    assert report.production_mutated is False
    assert report.auto_deployed is False
    assert report.final_state == AutonomyState.READY_FOR_REVIEW.value
    assert (tmp_path / f"{report.cycle_id}.md").is_file()


def test_failure_injection_matrix(tmp_path):
    modes = [
        ("TEST_FAILURE", {AutonomyState.LEARNED.value, AutonomyState.ABORTED.value}, True),
        ("BUILD_FAILURE", {AutonomyState.LEARNED.value, AutonomyState.ABORTED.value, AutonomyState.FAILED.value}, True),
        ("VERIFICATION_FAILURE", {AutonomyState.LEARNED.value, AutonomyState.ABORTED.value}, True),
        ("TIMEOUT", {AutonomyState.ABORTED.value}, False),
        ("RESOURCE_LIMIT", {AutonomyState.PAUSED_FOR_REVIEW.value}, False),
    ]
    for i, (mode, states, expect_rollback) in enumerate(modes):
        budget = AutonomyBudget(max_iterations=3, max_failed_attempts=5)
        loop = AutonomyLoop(
            target_root=TARGET,
            budget=budget,
            reports_dir=tmp_path / f"inj_{i}",
        )
        report = loop.run_cycle(inject=mode)  # type: ignore[arg-type]
        assert report.final_state in states, (mode, report.final_state, report.learning)
        if expect_rollback:
            assert report.rollback or "FAIL" in report.tests or "FAIL" in report.verification


def test_budget_pauses(tmp_path):
    budget = AutonomyBudget(max_iterations=1)
    loop = AutonomyLoop(target_root=TARGET, budget=budget, reports_dir=tmp_path)
    first = loop.run_cycle()
    assert first.final_state == AutonomyState.READY_FOR_REVIEW.value
    second = loop.run_cycle()
    assert second.final_state == AutonomyState.PAUSED_FOR_REVIEW.value

def test_learning_resets_after_pass(tmp_path):
    from autonomy.components import LearningStore

    store = LearningStore(tmp_path / "learn.jsonl")
    problem, proposal = "p", "fix"
    store.record({"fingerprint": f"{problem}::{proposal}", "result": "FAILED"})
    store.record({"fingerprint": f"{problem}::{proposal}", "result": "FAILED"})
    assert store.should_block(problem, proposal) is True
    store.record({"fingerprint": f"{problem}::{proposal}", "result": "PASSED"})
    assert store.should_block(problem, proposal) is False
    store.record({"fingerprint": f"{problem}::{proposal}", "result": "FAILED"})
    assert store.should_block(problem, proposal) is False  # only 1 fail since pass


def test_continuous_loop_respects_budget(tmp_path):
    budget = AutonomyBudget(max_iterations=2)
    loop = AutonomyLoop(target_root=TARGET, budget=budget, reports_dir=tmp_path)
    cycles = loop.run_until_budget()
    assert 1 <= len(cycles) <= 2
    assert all(c.production_mutated is False for c in cycles)
