"""Night 2 G21–G30 F7 controlled self-verification extensions."""

from __future__ import annotations

from pathlib import Path

from self_verification.f7_loop import F7ControlledLoop
from self_verification.learning import LearningMemory
from self_verification.models import RunStatus
from self_verification.planner import plan_improvement, score_improvement
from self_verification.system_observe import (
    ObservationKind,
    diagnose_observation,
    observe_system,
)
from self_verification.testgen import generate_bad_test_example, generate_regression_test


def test_g21_system_observation_normalize():
    obs = observe_system(
        test_failures=["Flutter widget test failed: UI init"],
        api_errors=["timeout /api/listings"],
        stale_symbols=["AAA"],
        dependency_ok=False,
        config_present=False,
        decision_stats={"win_rate": 0.2, "trades": 10, "consecutive_losses": 6, "cycles": 12, "no_trade_ratio": 0.99},
    )
    kinds = {o.kind for o in obs}
    assert ObservationKind.TEST_FAILURE in kinds
    assert ObservationKind.API_ERROR in kinds
    assert ObservationKind.STALE_DATA in kinds
    assert ObservationKind.BROKEN_DEPENDENCY in kinds
    assert ObservationKind.MISSING_CONFIGURATION in kinds
    assert ObservationKind.PERFORMANCE_DEGRADATION in kinds


def test_g22_root_cause_requires_evidence():
    obs = observe_system(test_failures=["Flutter UI initialization failure"])[0]
    diag = diagnose_observation(obs)
    assert diag.evidence
    assert diag.llm_trusted is False
    assert diag.category == "UI"
    d = diag.to_dict()
    assert d["evidence_required"] is True


def test_g23_planner_proposal_not_production():
    obs = observe_system(test_failures=["orphan file after image delete"])[0]
    diag = diagnose_observation(obs)
    prop = plan_improvement(obs, diag, tests_required=5)
    assert prop.applies_to_production is False
    assert prop.auto_apply is False
    assert prop.requires_human_approval is True
    assert prop.tests_required == 5
    assert "rollback" in prop.rollback.lower() or prop.rollback_available


def test_g25_testgen_quality_gates():
    good = generate_regression_test(
        problem="self_check broken",
        expected_behavior="self_check returns True",
    )
    assert good.accepted is True
    assert good.quality["syntax"]
    assert good.quality["assertion_quality"]
    bad = generate_bad_test_example()
    assert bad.accepted is False
    assert "missing_assertion" in bad.rejection_reasons


def test_g28_learning_blocks_repeat_failures(tmp_path):
    mem = LearningMemory(tmp_path / "learn.jsonl")
    for _ in range(2):
        mem.record_failure(
            problem="p1",
            diagnosis="d",
            proposal="fix_x",
            change="c",
            failure="tests_failed",
            root_cause="r",
            rollback="done",
            lesson="need new evidence",
        )
    assert mem.should_block_proposal("p1", "fix_x") is True
    assert mem.should_block_proposal("p1", "different_fix") is False


def test_g29_score_does_not_authorize_apply():
    sc = score_improvement(
        expected_benefit=0.9,
        risk="low",
        confidence=0.9,
        test_coverage=0.8,
        rollback_available=True,
        complexity=0.2,
    )
    assert 0.0 <= sc <= 1.0
    obs = observe_system(test_failures=["x"])[0]
    prop = plan_improvement(obs, diagnose_observation(obs))
    payload = prop.to_dict()
    assert payload["auto_apply"] is False
    assert payload["score_alone_does_not_authorize_apply"] is True
    assert "improvement_score" in payload


def test_g30_f7_full_loop_happy_and_rollback(tmp_path):
    loop = F7ControlledLoop(learning=LearningMemory(tmp_path / "l.jsonl"))
    happy = loop.run(
        test_failures=["intentional BROKEN self_check"],
        run_sandbox_fix=True,
        inject_failure=False,
        sandbox_root=tmp_path / "sb_ok",
    )
    assert happy.production_mutated is False
    assert happy.auto_deployed is False
    assert happy.verification is not None
    assert happy.verification["status"] == RunStatus.READY_FOR_REVIEW.value
    assert happy.proposals
    assert happy.generated_tests
    assert happy.to_dict()["stages_contract"]["LEARN"] is True

    fail = loop.run(
        test_failures=["bad patch path"],
        run_sandbox_fix=True,
        inject_failure=True,
        sandbox_root=tmp_path / "sb_fail",
    )
    assert fail.verification["status"] == RunStatus.ROLLED_BACK.value
    assert fail.verification["production_mutated"] is False
    # learning recorded
    assert loop.learning.all()
