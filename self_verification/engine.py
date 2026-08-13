"""Controlled self-verification engine (F7 foundation — not F8 autonomy)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .audit import AuditLog
from .models import (
    ChangeProposal,
    LoopStage,
    RunStatus,
    StageResult,
    VerificationReport,
    new_run_id,
)
from .probes import detect_defect, diagnose, observe_target
from .proposers import propose_bad_fix, propose_self_verification_fix
from .runner import run_sandbox_pytest
from .sandbox import Sandbox, SandboxError

# Production roots that must never be written by this engine
DEFAULT_PRODUCTION_GUARDS = (
    "changex/app",
    "changex_app/lib",
    "borsa_bot",
    "companion/app",
)


class SelfVerificationEngine:
    def __init__(
        self,
        *,
        target_source: Path | None = None,
        audit_path: Path | None = None,
        sandbox_root: Path | None = None,
        production_guards: list[Path] | None = None,
        allow_self_deployment: bool = False,
    ) -> None:
        pkg = Path(__file__).resolve().parent
        self.target_source = Path(target_source or (pkg / "target")).resolve()
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        if sandbox_root is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="sv_sandbox_")
            self.sandbox_root = Path(self._tmp.name)
        else:
            self.sandbox_root = Path(sandbox_root)
            self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(Path(audit_path or (self.sandbox_root / "audit.jsonl")))
        root = pkg.parents[0]
        self.production_guards = production_guards or [root / p for p in DEFAULT_PRODUCTION_GUARDS]
        # F8 hard off
        if allow_self_deployment:
            raise SandboxError(
                "SELF_DEPLOYMENT_FORBIDDEN",
                "Self-deployment / LIVE autonomy is disabled (F8 OFF)",
            )
        self.allow_self_deployment = False

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def _stage(
        self,
        report: VerificationReport,
        stage: LoopStage,
        ok: bool,
        detail: dict | None = None,
    ) -> StageResult:
        result = StageResult(stage=stage, ok=ok, detail=detail or {})
        report.stages.append(result)
        self.audit.write(
            run_id=report.run_id,
            stage=stage.value,
            ok=ok,
            detail=detail or {},
        )
        return result

    def run(
        self,
        *,
        proposal_factory: Callable[..., ChangeProposal] | None = None,
        inject_failure: bool = False,
    ) -> VerificationReport:
        """
        Execute the controlled loop.

        inject_failure=True → use a bad proposal to prove ROLLBACK.
        """
        report = VerificationReport(
            run_id=new_run_id(),
            status=RunStatus.RUNNING,
            sandbox_path=str(self.sandbox_root),
        )
        sandbox = Sandbox(self.sandbox_root, source_root=self.target_source)
        try:
            sandbox.assert_not_production(self.production_guards)
            # Copy target + tests into sandbox
            sandbox.sync_from_source(["module.py", "EXPECTED.txt", "test_target.py"])

            # OBSERVE
            obs = observe_target(self.sandbox_root)
            self._stage(
                report,
                LoopStage.OBSERVE,
                True,
                {"markers": obs.markers, "files": list(obs.files)},
            )

            # DETECT
            detection = detect_defect(obs)
            self._stage(
                report,
                LoopStage.DETECT,
                True,
                {
                    "defect_found": detection.defect_found,
                    "code": detection.code,
                    "message": detection.message,
                },
            )
            if not detection.defect_found:
                report.status = RunStatus.READY_FOR_REVIEW
                report.ready_for_review = True
                self._stage(report, LoopStage.REPORT, True, {"note": "already healthy"})
                return report

            # DIAGNOSE
            diagnosis = diagnose(detection)
            self._stage(
                report,
                LoopStage.DIAGNOSE,
                True,
                {
                    "root_cause": diagnosis.root_cause,
                    "suggested_fix": diagnosis.suggested_fix,
                    "confidence": diagnosis.confidence,
                },
            )

            # PLAN
            plan = {
                "steps": [
                    "Create ChangeProposal (no production write)",
                    "Apply patches only inside sandbox",
                    "Run sandbox pytest",
                    "VERIFY → READY_FOR_REVIEW or ROLLBACK",
                ],
                "forbidden": ["production mutate", "self-deploy", "LIVE autonomy"],
            }
            self._stage(report, LoopStage.PLAN, True, plan)

            # PROPOSE CHANGE
            if proposal_factory is not None:
                proposal = proposal_factory(obs, diagnosis)
            elif inject_failure:
                proposal = propose_bad_fix(obs)
            else:
                proposal = propose_self_verification_fix(obs, diagnosis)
            # Enforce sandbox-only flags
            proposal.applies_to_production = False
            proposal.deployment_allowed = False
            report.proposal = proposal
            self._stage(
                report,
                LoopStage.PROPOSE_CHANGE,
                True,
                {"proposal": proposal.to_dict()},
            )

            # APPLY SANDBOX (never production)
            sandbox.apply_proposal(proposal)
            self._stage(
                report,
                LoopStage.APPLY_SANDBOX,
                True,
                {"patched": [p.path for p in proposal.patches]},
            )
            report.production_mutated = False

            # RUN TESTS
            ok, output = run_sandbox_pytest(self.sandbox_root)
            report.test_output = output
            self._stage(
                report,
                LoopStage.RUN_TESTS,
                ok,
                {"return_ok": ok, "output_tail": output[-1500:]},
            )

            # VERIFY
            verified = bool(ok)
            if ok:
                body = sandbox.read("module.py")
                verified = (
                    'MARKER = "VERIFIED_OK"' in body
                    and "def self_check" in body
                    and "return False  # intentional defect" not in body
                )
            self._stage(
                report,
                LoopStage.VERIFY,
                verified,
                {"verified": verified, "tests_ok": ok},
            )

            if ok and verified:
                report.status = RunStatus.READY_FOR_REVIEW
                report.ready_for_review = True
                self._stage(
                    report,
                    LoopStage.REPORT,
                    True,
                    {
                        "status": report.status.value,
                        "message": "Sandbox fix verified — READY_FOR_REVIEW (no auto-deploy)",
                    },
                )
                return report

            # ROLLBACK IF FAILED
            restored = sandbox.rollback()
            # After rollback, module should match pre-patch snapshot
            self._stage(
                report,
                LoopStage.ROLLBACK,
                True,
                {"restored": restored},
            )
            # Confirm rollback restored defect (for failure injection) or prior content
            post = sandbox.read("module.py")
            report.status = RunStatus.ROLLED_BACK
            report.ready_for_review = False
            self._stage(
                report,
                LoopStage.REPORT,
                True,
                {
                    "status": report.status.value,
                    "message": "Tests/verify failed — sandbox rolled back; production untouched",
                    "module_still_broken": "BROKEN" in post or "intentional defect" in post,
                },
            )
            return report
        except SandboxError as exc:
            report.status = RunStatus.BLOCKED if exc.code.endswith("FORBIDDEN") else RunStatus.FAILED
            report.error = f"{exc.code}: {exc.message}"
            self._stage(
                report,
                LoopStage.REPORT,
                False,
                {"error": report.error, "status": report.status.value},
            )
            return report
        except Exception as exc:  # noqa: BLE001
            report.status = RunStatus.FAILED
            report.error = str(exc)
            try:
                sandbox.rollback()
                self._stage(report, LoopStage.ROLLBACK, True, {"emergency": True})
            except Exception:  # noqa: BLE001
                pass
            self._stage(
                report,
                LoopStage.REPORT,
                False,
                {"error": report.error, "status": report.status.value},
            )
            return report


def run_self_verification(
    *,
    inject_failure: bool = False,
    sandbox_root: Path | None = None,
    audit_path: Path | None = None,
    keep_sandbox: bool = False,
) -> VerificationReport:
    """Convenience entry — always sandbox-only, never deploys."""
    engine = SelfVerificationEngine(sandbox_root=sandbox_root, audit_path=audit_path)
    try:
        return engine.run(inject_failure=inject_failure)
    finally:
        if sandbox_root is None and not keep_sandbox:
            engine.close()
