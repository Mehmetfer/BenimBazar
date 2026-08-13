"""GÖREV 28 — Learning memory for failed improvement attempts (no auto production mutation)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LearningRecord:
    problem: str
    diagnosis: str
    proposal: str
    change: str
    failure: str
    root_cause: str
    rollback: str
    lesson: str
    fingerprint: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fingerprint(problem: str, proposal: str) -> str:
    return f"{problem.strip().lower()}::{proposal.strip().lower()}"[:240]


class LearningMemory:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path("self_verification/.learning_memory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[LearningRecord] = []

    def record_failure(
        self,
        *,
        problem: str,
        diagnosis: str,
        proposal: str,
        change: str,
        failure: str,
        root_cause: str,
        rollback: str,
        lesson: str,
    ) -> LearningRecord:
        rec = LearningRecord(
            problem=problem,
            diagnosis=diagnosis,
            proposal=proposal,
            change=change,
            failure=failure,
            root_cause=root_cause,
            rollback=rollback,
            lesson=lesson,
            fingerprint=fingerprint(problem, proposal),
        )
        self._records.append(rec)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        return rec

    def all(self) -> List[LearningRecord]:
        if self._records:
            return list(self._records)
        if not self.path.exists():
            return []
        out: List[LearningRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(LearningRecord(**json.loads(line)))
        self._records = out
        return list(out)

    def should_block_proposal(self, problem: str, proposal: str, *, max_fails: int = 2) -> bool:
        """Prevent repeatedly retrying the same failed proposal automatically."""
        fp = fingerprint(problem, proposal)
        fails = sum(1 for r in self.all() if r.fingerprint == fp)
        return fails >= max_fails

    def lesson_for(self, problem: str) -> Optional[str]:
        matches = [r for r in self.all() if r.problem.strip().lower() == problem.strip().lower()]
        if not matches:
            return None
        return matches[-1].lesson
