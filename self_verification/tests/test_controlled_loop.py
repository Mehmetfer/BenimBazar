"""Unit + integration tests for F7 controlled self-verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from self_verification.audit import AuditLog
from self_verification.engine import SelfVerificationEngine
from self_verification.models import LoopStage, RunStatus
from self_verification.probes import detect_defect, diagnose, observe_target
from self_verification.proposers import propose_bad_fix, propose_self_verification_fix
from self_verification.sandbox import Sandbox, SandboxError


PKG = Path(__file__).resolve().parents[1]
TARGET = PKG / "target"


def test_observe_detect_diagnose_unit():
    obs = observe_target(TARGET)
    assert obs.markers["has_module"]
    assert obs.markers["broken_marker"] or "intentional defect" in obs.files["module.py"]
    det = detect_defect(obs)
    assert det.defect_found
    assert det.code == "SELF_CHECK_FAILING"
    diag = diagnose(det)
    assert "BROKEN" in diag.root_cause or "defect" in diag.root_cause.lower()


def test_proposal_never_targets_production():
    obs = observe_target(TARGET)
    det = detect_defect(obs)
    prop = propose_self_verification_fix(obs, diagnose(det))
    assert prop.applies_to_production is False
    assert prop.deployment_allowed is False
    assert "VERIFIED_OK" in prop.patches[0].new_content


def test_sandbox_rejects_production_flags(tmp_path):
    sb = Sandbox(tmp_path / "s", source_root=TARGET)
    sb.sync_from_source(["module.py"])
    obs = observe_target(tmp_path / "s")
    prop = propose_self_verification_fix(obs, diagnose(detect_defect(obs)))
    prop.applies_to_production = True
    with pytest.raises(SandboxError) as ei:
        sb.apply_proposal(prop)
    assert ei.value.code == "PRODUCTION_MUTATE_FORBIDDEN"


def test_audit_log_appends_stages(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.write(run_id="r1", stage="OBSERVE", ok=True, detail={"x": 1})
    log.write(run_id="r1", stage="DETECT", ok=True)
    rows = log.for_run("r1")
    assert len(rows) == 2
    assert rows[0]["stage"] == "OBSERVE"
    assert json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])["detail"]["x"] == 1


def test_engine_happy_path_ready_for_review(tmp_path):
    sandbox = tmp_path / "sb"
    audit = tmp_path / "audit.jsonl"
    engine = SelfVerificationEngine(sandbox_root=sandbox, audit_path=audit)
    report = engine.run(inject_failure=False)
    assert report.status == RunStatus.READY_FOR_REVIEW
    assert report.ready_for_review is True
    assert report.production_mutated is False
    assert report.proposal is not None
    stages = [s.stage for s in report.stages]
    assert LoopStage.OBSERVE in stages
    assert LoopStage.DETECT in stages
    assert LoopStage.DIAGNOSE in stages
    assert LoopStage.PLAN in stages
    assert LoopStage.PROPOSE_CHANGE in stages
    assert LoopStage.APPLY_SANDBOX in stages
    assert LoopStage.RUN_TESTS in stages
    assert LoopStage.VERIFY in stages
    assert LoopStage.REPORT in stages
    # Proposal must precede apply in audit order
    audit_rows = AuditLog(audit).for_run(report.run_id)
    names = [r["stage"] for r in audit_rows]
    assert names.index("PROPOSE_CHANGE") < names.index("APPLY_SANDBOX")
    # Sandbox fixed; production target still broken
    assert "VERIFIED_OK" in (sandbox / "module.py").read_text()
    assert "BROKEN" in (TARGET / "module.py").read_text() or "intentional defect" in (
        TARGET / "module.py"
    ).read_text()


def test_failure_injection_triggers_rollback(tmp_path):
    sandbox = tmp_path / "sb_fail"
    audit = tmp_path / "audit_fail.jsonl"
    engine = SelfVerificationEngine(sandbox_root=sandbox, audit_path=audit)
    # Snapshot of broken content before run
    original = (TARGET / "module.py").read_text()
    report = engine.run(inject_failure=True)
    assert report.status == RunStatus.ROLLED_BACK
    assert report.ready_for_review is False
    stages = [s.stage for s in report.stages]
    assert LoopStage.ROLLBACK in stages
    assert LoopStage.RUN_TESTS in stages
    # After rollback, sandbox module matches pre-patch (still defective)
    restored = (sandbox / "module.py").read_text()
    assert restored == original or "intentional defect" in restored or "BROKEN" in restored
    # Production untouched
    assert (TARGET / "module.py").read_text() == original
    audit_rows = AuditLog(audit).for_run(report.run_id)
    assert any(r["stage"] == "ROLLBACK" and r["ok"] for r in audit_rows)


def test_self_deployment_flag_blocked(tmp_path):
    with pytest.raises(SandboxError) as ei:
        SelfVerificationEngine(
            sandbox_root=tmp_path / "x",
            allow_self_deployment=True,
        )
    assert ei.value.code == "SELF_DEPLOYMENT_FORBIDDEN"


def test_report_autonomy_flags(tmp_path):
    engine = SelfVerificationEngine(sandbox_root=tmp_path / "sb2", audit_path=tmp_path / "a2.jsonl")
    report = engine.run()
    payload = report.to_dict()
    assert payload["autonomy"]["self_verification"] is True
    assert payload["autonomy"]["self_deployment"] is False
    assert payload["autonomy"]["live_autonomy"] is False
    assert payload["autonomy"]["f8"] == "DISABLED"


def test_custom_bad_proposal_factory_rolls_back(tmp_path):
    engine = SelfVerificationEngine(sandbox_root=tmp_path / "sb3", audit_path=tmp_path / "a3.jsonl")

    def factory(obs, diagnosis):
        return propose_bad_fix(obs)

    report = engine.run(proposal_factory=factory)
    assert report.status == RunStatus.ROLLED_BACK
