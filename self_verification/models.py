"""Self-verification loop models — proposal ≠ production mutate."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class LoopStage(str, Enum):
    OBSERVE = "OBSERVE"
    DETECT = "DETECT"
    DIAGNOSE = "DIAGNOSE"
    PLAN = "PLAN"
    PROPOSE_CHANGE = "PROPOSE_CHANGE"
    APPLY_SANDBOX = "APPLY_SANDBOX"  # sandbox only — never production
    RUN_TESTS = "RUN_TESTS"
    VERIFY = "VERIFY"
    ROLLBACK = "ROLLBACK"
    REPORT = "REPORT"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"  # e.g. deployment autonomy requested


@dataclass
class FilePatch:
    """Relative path inside the sandbox target tree."""

    path: str
    old_content: str
    new_content: str
    description: str = ""


@dataclass
class ChangeProposal:
    """Human/reviewable proposal — must exist BEFORE any sandbox write."""

    proposal_id: str
    title: str
    rationale: str
    patches: list[FilePatch]
    target: str = "self-verification"
    created_at: float = field(default_factory=time.time)
    applies_to_production: bool = False  # hard false — sandbox only
    deployment_allowed: bool = False  # F8 off

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "rationale": self.rationale,
            "target": self.target,
            "created_at": self.created_at,
            "applies_to_production": False,
            "deployment_allowed": False,
            "patches": [
                {
                    "path": p.path,
                    "description": p.description,
                    "old_sha_len": len(p.old_content),
                    "new_sha_len": len(p.new_content),
                    "old_preview": p.old_content[:120],
                    "new_preview": p.new_content[:120],
                }
                for p in self.patches
            ],
        }


@dataclass
class StageResult:
    stage: LoopStage
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "ok": self.ok,
            "detail": self.detail,
            "ts": self.ts,
        }


@dataclass
class VerificationReport:
    run_id: str
    status: RunStatus
    stages: list[StageResult] = field(default_factory=list)
    proposal: ChangeProposal | None = None
    test_output: str = ""
    error: str = ""
    sandbox_path: str = ""
    production_mutated: bool = False
    ready_for_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "stages": [s.to_dict() for s in self.stages],
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "test_output": self.test_output[-4000:],
            "error": self.error,
            "sandbox_path": self.sandbox_path,
            "production_mutated": self.production_mutated,
            "ready_for_review": self.ready_for_review,
            "autonomy": {
                "self_verification": True,
                "self_deployment": False,
                "live_autonomy": False,
                "f8": "DISABLED",
            },
        }


def new_run_id() -> str:
    return f"sv-{uuid.uuid4().hex[:12]}"


def new_proposal_id() -> str:
    return f"prop-{uuid.uuid4().hex[:10]}"
