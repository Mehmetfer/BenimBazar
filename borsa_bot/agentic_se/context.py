"""Long-run task context — resume-friendly state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TaskContext:
    goal_id: str
    goal: str
    stage: str
    completed: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    failed_attempts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TaskContext:
        return cls(**{k: raw[k] for k in cls.__dataclass_fields__ if k in raw})


class ContextStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.path = self.root / "agentic_se" / "data" / "task_context.json"

    def save(self, ctx: TaskContext) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ctx.updated_at = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(ctx.to_dict(), indent=2), encoding="utf-8")

    def load(self) -> TaskContext | None:
        if not self.path.is_file():
            return None
        return TaskContext.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
