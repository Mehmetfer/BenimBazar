"""Learning from SI attempts — failures become reusable lessons."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomy.lessons import Lesson, save_lesson

ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS_DIR = ROOT / "self_improvement" / "data" / "attempts"


@dataclass
class AttemptRecord:
    attempt_id: str
    problem: str
    hypothesis: str
    change: str
    tests: list[str] = field(default_factory=list)
    failure: str = ""
    root_cause: str = ""
    lesson: str = ""
    rollback: bool = False
    alternative: str = ""
    accepted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def save_attempt(rec: AttemptRecord) -> Path:
    ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ATTEMPTS_DIR / f"{rec.attempt_id}.json"
    path.write_text(json.dumps(rec.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def list_attempts() -> list[AttemptRecord]:
    if not ATTEMPTS_DIR.is_dir():
        return []
    out: list[AttemptRecord] = []
    for p in sorted(ATTEMPTS_DIR.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        out.append(AttemptRecord(**{k: raw[k] for k in AttemptRecord.__dataclass_fields__ if k in raw}))
    return out


def promote_failure_to_lesson(rec: AttemptRecord) -> Path | None:
    if rec.accepted or not rec.failure:
        return None
    lesson = Lesson(
        id=f"si-{rec.attempt_id}",
        title=(rec.lesson or rec.problem)[:120],
        error_class="SELF_IMPROVEMENT_FAILURE",
        root_cause=rec.root_cause or "unspecified",
        fix_summary=rec.alternative or rec.change[:200],
        regression_test="tests/test_self_improvement.py",
        architectural_decision=rec.lesson or "Record SI failure; do not repeat without new hypothesis",
        prevents=["repeat_same_failed_patch"],
    )
    return save_lesson(lesson)
