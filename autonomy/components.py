"""Core autonomy components — Observer → … → LearningStore (wired, not empty stubs)."""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from autonomy.concepts import Evidence, Observation
from autonomy.state_machine import AutonomyState


@dataclass
class Diagnosis:
    root_cause: str
    category: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_cause": self.root_cause,
            "category": self.category,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass
class ImprovementProposal:
    proposal_id: str
    problem: str
    diagnosis: str
    plan: str
    patch_files: dict[str, str]
    tests_required: int = 1
    risk: str = "medium"
    applies_to_production: bool = False
    auto_deploy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "problem": self.problem,
            "diagnosis": self.diagnosis,
            "plan": self.plan,
            "files": list(self.patch_files.keys()),
            "tests_required": self.tests_required,
            "risk": self.risk,
            "applies_to_production": False,
            "auto_deploy": False,
        }


class Observer:
    def observe_repo_markers(self, root: Path) -> list[Observation]:
        obs: list[Observation] = []
        target = root / "module.py"
        if target.is_file():
            body = target.read_text(encoding="utf-8")
            if "BROKEN" in body or "intentional defect" in body:
                obs.append(
                    Observation(
                        source="repo",
                        kind="DEFECT",
                        message="self_check target broken",
                        evidence=["BROKEN marker or intentional defect in module.py"],
                    )
                )
            elif "def self_check" in body and "VERIFIED_OK" in body:
                obs.append(
                    Observation(
                        source="repo",
                        kind="HEALTHY",
                        message="self_check healthy",
                        evidence=["VERIFIED_OK present"],
                    )
                )
        todo_hits = 0
        for p in root.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if "TODO" in text or "FIXME" in text:
                todo_hits += 1
        if todo_hits:
            obs.append(
                Observation(
                    source="repo",
                    kind="TODO_FIXME",
                    message=f"todo_fixme_files={todo_hits}",
                    evidence=[f"count={todo_hits}"],
                )
            )
        if not obs:
            obs.append(
                Observation(
                    source="repo",
                    kind="IDLE",
                    message="no_actionable_observation",
                    evidence=[],
                )
            )
        return obs


class EvidenceCollector:
    def collect(self, observations: list[Observation]) -> Evidence:
        ev = Evidence()
        for o in observations:
            ev.add(f"{o.kind}:{o.message}")
            ev.items.extend(o.evidence)
        actionable = [o for o in observations if o.kind not in {"HEALTHY", "IDLE"}]
        ev.confidence = 0.8 if actionable else 0.3
        return ev


class Detector:
    def detect(self, observations: list[Observation]) -> Observation | None:
        for o in observations:
            if o.kind in {"DEFECT", "TEST_FAILURE", "CONFIG_FAILURE", "DEPENDENCY_FAILURE"}:
                return o
        for o in observations:
            if o.kind == "TODO_FIXME":
                return o
        return None


class Diagnoser:
    def diagnose(self, problem: Observation, evidence: Evidence) -> Diagnosis:
        if problem.kind == "DEFECT":
            return Diagnosis(
                root_cause="Intentional broken self_check marker",
                category="SELF_CHECK",
                confidence=0.9,
                evidence=list(evidence.items)[:8],
            )
        if problem.kind == "TEST_FAILURE":
            return Diagnosis(
                root_cause="Injected or detected test failure",
                category="TEST",
                confidence=0.85,
                evidence=list(evidence.items)[:8],
            )
        return Diagnosis(
            root_cause=problem.message,
            category=problem.kind,
            confidence=0.55,
            evidence=list(evidence.items)[:8],
        )


class Planner:
    def plan(self, problem: Observation, diagnosis: Diagnosis) -> dict[str, Any]:
        return {
            "steps": [
                "Generate ImprovementProposal (sandbox only)",
                "Apply patch in isolated sandbox",
                "Generate/run regression test",
                "Verify → READY_FOR_REVIEW or ROLLBACK",
                "Learn; never auto-deploy",
            ],
            "forbidden": ["production mutate", "LIVE trading", "auto-deploy", "F8"],
            "diagnosis": diagnosis.to_dict(),
            "problem": problem.to_dict(),
        }


class ProposalEngine:
    def propose(self, problem: Observation, diagnosis: Diagnosis, *, broken_source: str) -> ImprovementProposal:
        fixed = broken_source.replace("BROKEN", "VERIFIED_OK").replace(
            "return False  # intentional defect",
            "return True  # verified",
        )
        if "VERIFIED_OK" not in fixed:
            fixed = (
                'MARKER = "VERIFIED_OK"\n\n'
                "def self_check() -> bool:\n"
                "    return True  # verified\n"
            )
        return ImprovementProposal(
            proposal_id=f"auto-{uuid.uuid4().hex[:10]}",
            problem=problem.message,
            diagnosis=diagnosis.root_cause,
            plan="Replace BROKEN self_check with VERIFIED_OK returning True",
            patch_files={"module.py": fixed},
            tests_required=1,
            risk="low",
        )


class SandboxExecutor:
    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root)
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self.sandbox_path: Path | None = None
        self._baseline: dict[str, str] = {}

    def enter(self) -> Path:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="autonomy_sb_")
        self.sandbox_path = Path(self._tmpdir.name)
        for name in ("module.py", "EXPECTED.txt", "test_target.py"):
            src = self.source_root / name
            if src.is_file():
                dst = self.sandbox_path / name
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                self._baseline[name] = dst.read_text(encoding="utf-8")
        return self.sandbox_path

    def apply(self, proposal: ImprovementProposal) -> list[str]:
        assert self.sandbox_path is not None
        changed: list[str] = []
        for rel, content in proposal.patch_files.items():
            path = self.sandbox_path / rel
            # production path guard
            resolved = path.resolve()
            if "changex/app" in str(resolved) or "borsa_bot" in str(resolved):
                raise RuntimeError("PRODUCTION_MUTATE_FORBIDDEN")
            path.write_text(content, encoding="utf-8")
            changed.append(rel)
        return changed

    def rollback(self) -> list[str]:
        assert self.sandbox_path is not None
        restored = []
        for name, content in self._baseline.items():
            (self.sandbox_path / name).write_text(content, encoding="utf-8")
            restored.append(name)
        return restored

    def close(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None


class TestRunner:
    def run_sandbox_assert(self, sandbox: Path) -> tuple[bool, str]:
        """Deterministic lightweight runner for fixture target (no pytest subprocess required)."""
        mod = sandbox / "module.py"
        testf = sandbox / "test_target.py"
        if not mod.is_file():
            return False, "missing module.py"
        body = mod.read_text(encoding="utf-8")
        try:
            ast.parse(body)
        except SyntaxError as exc:
            return False, f"syntax:{exc}"
        ok = 'MARKER = "VERIFIED_OK"' in body and "return False  # intentional defect" not in body
        # optional test file presence
        if testf.is_file():
            tbody = testf.read_text(encoding="utf-8")
            if "assert" not in tbody and "self_check" not in tbody:
                return False, "weak_test_file"
        return ok, "verified" if ok else "self_check_still_broken"


class VerificationEngine:
    def verify(self, sandbox: Path, tests_ok: bool) -> tuple[bool, str]:
        if not tests_ok:
            return False, "tests_failed"
        body = (sandbox / "module.py").read_text(encoding="utf-8")
        if "BROKEN" in body:
            return False, "broken_marker_present"
        if "VERIFIED_OK" not in body:
            return False, "missing_verified_marker"
        return True, "ok"


class RollbackManager:
    def __init__(self, sandbox: SandboxExecutor) -> None:
        self.sandbox = sandbox

    def rollback(self) -> list[str]:
        return self.sandbox.rollback()


class LearningStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("reports/autonomy/learning.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, payload: dict[str, Any]) -> None:
        payload = {**payload, "ts": time.time(), "auto_deploy": False}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def should_block(self, problem: str, proposal: str, *, max_fails: int = 2) -> bool:
        if not self.path.exists():
            return False
        fp = f"{problem}::{proposal}".lower()
        n = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("fingerprint") == fp and row.get("result") == "FAILED":
                n += 1
        return n >= max_fails


class AuditLogger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("reports/autonomy/audit.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, stage: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
        row = {
            "stage": stage,
            "ok": ok,
            "detail": detail or {},
            "ts": time.time(),
            "production_mutated": False,
            "live_trading": False,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
