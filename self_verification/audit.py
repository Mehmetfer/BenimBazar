"""Append-only audit log for every self-verification stage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def write(self, *, run_id: str, stage: str, ok: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {
            "ts": time.time(),
            "run_id": run_id,
            "stage": stage,
            "ok": ok,
            "detail": detail or {},
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out

    def for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [e for e in self.read_all() if e.get("run_id") == run_id]
