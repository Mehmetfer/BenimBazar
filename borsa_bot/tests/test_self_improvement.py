"""Self-improvement engine tests — audit, plan, impl, verify, rollback, safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from self_improvement.audit import Severity, audit_repository
from self_improvement.backlog import BacklogStore, ImprovementItem
from self_improvement.engine import SelfImprovementEngine, bootstrap_baseline
from self_improvement.invariants import (
    FROZEN_PRODUCTION_INVARIANTS,
    SafetyViolation,
    assert_invariant_untouched,
    path_allowed_for_auto_impl,
)
from self_improvement.learn import AttemptRecord, promote_failure_to_lesson, save_attempt
from self_improvement.reviewer import review_change
from self_improvement.risk import assess_change_risk
from self_improvement.sandbox import Sandbox
from self_improvement.scorecard import score_self_improvement
from self_improvement.stop import evaluate_stop
from self_improvement.verify import parse_pytest_summary, save_baseline, verify_against_baseline


def test_si1_audit_finds_structured_findings():
    findings = audit_repository(max_findings=50)
    assert isinstance(findings, list)
    assert all(hasattr(f, "severity") for f in findings)
    # domain invariants file exists → should not CRITICAL-missing
    assert not any(f.title.startswith("Missing domain invariant") for f in findings)


def test_si2_backlog_from_findings(tmp_path: Path):
    store = BacklogStore(tmp_path / "backlog.json")
    item = store.add(
        ImprovementItem(
            id=store.next_id(),
            title="Provider failure recovery weak",
            priority="Recovery",
            severity="HIGH",
            category="recovery",
        )
    )
    assert item.id == "IMPROVEMENT-001"
    assert store.select_next() is not None


def test_allowlist_blocks_risk_and_kill_switch():
    assert path_allowed_for_auto_impl("self_improvement/health.py")
    assert not path_allowed_for_auto_impl("risk/engine.py")
    assert not path_allowed_for_auto_impl("trading_safety/kill_switch.py")
    assert not path_allowed_for_auto_impl("config/settings.py")
    with pytest.raises(SafetyViolation):
        assert_invariant_untouched({"risk/engine.py": "x = 1"})
    with pytest.raises(SafetyViolation):
        assert_invariant_untouched({"self_improvement/x.py": "kill_switch_active=False"})


def test_frozen_invariants_present():
    assert "kill_switch_no_new_orders" in FROZEN_PRODUCTION_INVARIANTS
    assert "live_broker_default_locked" in FROZEN_PRODUCTION_INVARIANTS
    assert "no_test_deletion" in FROZEN_PRODUCTION_INVARIANTS


def test_change_risk_elevates_trading_paths():
    low = assess_change_risk(["self_improvement/health.py"], touches_tests=True)
    assert low.band in {"LOW", "MODERATE"}
    high = assess_change_risk(["trading_safety/order_gate.py"], touches_tests=False, category="Safety")
    assert high.score >= 70
    assert high.requires_expanded_suite


def test_sandbox_rollback(tmp_path: Path):
    root = tmp_path
    (root / "self_improvement" / "data" / "snapshots").mkdir(parents=True)
    sb = Sandbox(root)
    target = root / "self_improvement" / "demo.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ORIGINAL\n", encoding="utf-8")
    sb.begin("iteration-test")
    sb.capture_before(["self_improvement/demo.py"])
    sb.apply_writes({"self_improvement/demo.py": "BROKEN\n"})
    assert target.read_text(encoding="utf-8") == "BROKEN\n"
    rb = sb.rollback()
    assert rb.rolled_back is True
    assert target.read_text(encoding="utf-8") == "ORIGINAL\n"


def test_reviewer_rejects_no_benefit_and_critical():
    r = review_change(
        paths=["self_improvement/x.py"],
        diff_summary="noop",
        risk_score=90,
        has_tests=False,
        measurable_benefit=False,
    )
    assert r.approved is False
    assert r.blockers


def test_stop_conditions_safe_stop():
    d = evaluate_stop(critical_regression=True)
    assert d.stop and d.kind == "SAFE_STOP"
    d2 = evaluate_stop(repeated_failed_attempts=3)
    assert d2.stop


def test_parse_pytest_and_baseline_guard(tmp_path: Path, monkeypatch):
    assert parse_pytest_summary("395 passed, 4 warnings in 1.0s") == (395, 0)
    assert parse_pytest_summary("10 failed, 2 passed")[1] == 10
    # point baseline path via save in real module — use engine bootstrap
    from self_improvement import verify as verify_mod

    monkeypatch.setattr(verify_mod, "BASELINE_PATH", tmp_path / "baseline.json")
    save_baseline(passed=395, failed=0, note="test")
    assert verify_mod.load_baseline()["passed"] == 395


def test_learning_promotes_lesson(tmp_path: Path, monkeypatch):
    from self_improvement import learn as learn_mod

    monkeypatch.setattr(learn_mod, "ATTEMPTS_DIR", tmp_path / "attempts")
    rec = AttemptRecord(
        attempt_id="att1",
        problem="bad patch",
        hypothesis="x",
        change="self_improvement/x.py",
        failure="boom",
        root_cause="timeout without idempotency",
        lesson="Execution retry changes require idempotency regression suite",
        rollback=True,
        accepted=False,
    )
    save_attempt(rec)
    path = promote_failure_to_lesson(rec)
    assert path is not None
    assert path.is_file()


def test_scorecard_not_inflated_to_10_or_live():
    sc = score_self_improvement(
        si1_audit=True,
        si2_planning=True,
        si3_implementation=True,
        si4_testing=True,
        si5_regression=True,
        si6_recovery=True,
        si7_learning=True,
        si8_optimization=False,
        si9_architecture=False,
        si10_continuous=True,
    )
    assert sc.self_improvement_level <= 9.2
    assert sc.live_money_autonomy == "NOT VERIFIED"
    assert sc.full_level8_claimed is False
    assert all(g.id.startswith("SI-") for g in sc.gates)


def test_adversarial_si_cannot_write_kill_switch():
    with pytest.raises(SafetyViolation):
        assert_invariant_untouched(
            {
                "trading_safety/kill_switch.py": "class KillSwitch: pass",
            }
        )


def test_engine_iteration_baseline_guard_accepts():
    bootstrap_baseline(395)
    eng = SelfImprovementEngine()
    rep = eng.run_iteration(force_baseline_guard=True, expanded_verify=False)
    assert rep.waited_for_human is False
    assert rep.status == "ACCEPTED", rep.detail
    # If guard already exists, still ACCEPTED after rewrite/verify (idempotent)
    from self_improvement.baseline_guard import assert_baseline_not_regressed

    assert_baseline_not_regressed("395 passed in 1s", baseline_passed=395)
    with pytest.raises(AssertionError):
        assert_baseline_not_regressed("300 passed in 1s", baseline_passed=395)
    assert (Path(__file__).resolve().parents[1] / "self_improvement" / "baseline_guard.py").is_file()


def test_engine_rejects_and_rolls_back_on_bad_verify(tmp_path: Path, monkeypatch):
    """Inject verify failure → must rollback."""
    root = tmp_path
    (root / "self_improvement" / "data").mkdir(parents=True)
    (root / "tests").mkdir()
    # minimal package
    (root / "self_improvement" / "__init__.py").write_text("", encoding="utf-8")
    eng = SelfImprovementEngine(root=root)
    eng.backlog.add(
        ImprovementItem(
            id="IMPROVEMENT-001",
            title="Baseline pytest guard missing",
            priority="Correctness",
            severity="HIGH",
            category="missing_tests",
            notes="baseline_guard",
        )
    )

    def fake_verify(**kwargs):
        from self_improvement.verify import VerifyResult

        return VerifyResult(ok=False, passed=0, failed=1, baseline_passed=395, regression=True, detail="fail")

    monkeypatch.setattr("self_improvement.engine.verify_against_baseline", fake_verify)
    monkeypatch.setattr("self_improvement.engine.audit_repository", lambda root=None, max_findings=200: [])
    rep = eng.run_iteration(force_baseline_guard=True)
    assert rep.status == "REJECTED"
    assert rep.rollback is True
