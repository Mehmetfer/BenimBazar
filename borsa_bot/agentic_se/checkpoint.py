"""Safe checkpoints for ASE runs."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Checkpoint:
    id: str
    label: str
    created_at: str
    files: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.dir = self.root / "agentic_se" / "data" / "checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._stack: list[Checkpoint] = []

    def save(self, label: str, rel_paths: list[str]) -> Checkpoint:
        files: dict[str, str] = {}
        for rel in rel_paths:
            p = self.root / rel
            files[rel] = p.read_text(encoding="utf-8") if p.is_file() else ""
        cp = Checkpoint(
            id=f"cp-{uuid4().hex[:8]}",
            label=label,
            created_at=datetime.now(timezone.utc).isoformat(),
            files=files,
        )
        dest = self.dir / cp.id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "meta.json").write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")
        for rel, content in files.items():
            blob = dest / (rel.replace("/", "__") + ".blob")
            blob.write_text(content, encoding="utf-8")
        self._stack.append(cp)
        return cp

    def restore(self, checkpoint_id: str | None = None) -> Checkpoint:
        cp = None
        if checkpoint_id:
            for c in self._stack:
                if c.id == checkpoint_id:
                    cp = c
                    break
            if cp is None:
                meta = self.dir / checkpoint_id / "meta.json"
                raw = json.loads(meta.read_text(encoding="utf-8"))
                cp = Checkpoint(**{k: raw[k] for k in Checkpoint.__dataclass_fields__ if k in raw})
        else:
            if not self._stack:
                raise RuntimeError("no checkpoint")
            cp = self._stack[-1]
        for rel, content in cp.files.items():
            path = self.root / rel
            if content == "":
                if path.is_file():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return cp
