"""Sandbox snapshots + rollback for SI iterations (transaction-like)."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "self_improvement" / "data" / "snapshots"


@dataclass
class Snapshot:
    iteration_id: str
    created_at: str
    files: dict[str, str]  # rel_path -> content before change
    branch_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SandboxResult:
    ok: bool
    iteration_id: str
    rolled_back: bool = False
    detail: str = ""
    changed_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Sandbox:
    """File-level snapshot sandbox (no production mutate outside allowlist)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.snap_root = self.root / "self_improvement" / "data" / "snapshots"
        self.snap_root.mkdir(parents=True, exist_ok=True)
        self._current: Snapshot | None = None

    def begin(self, iteration_id: str | None = None) -> Snapshot:
        iid = iteration_id or f"iteration-{uuid4().hex[:8]}"
        self._current = Snapshot(
            iteration_id=iid,
            created_at=datetime.now(timezone.utc).isoformat(),
            files={},
            branch_name=f"self-improvement/{iid}",
        )
        return self._current

    def capture_before(self, rel_paths: list[str]) -> None:
        assert self._current is not None
        for rel in rel_paths:
            path = self.root / rel
            if path.is_file():
                self._current.files[rel] = path.read_text(encoding="utf-8")
            else:
                self._current.files[rel] = ""  # did not exist

    def persist_snapshot(self) -> Path:
        assert self._current is not None
        dest = self.snap_root / self._current.iteration_id
        dest.mkdir(parents=True, exist_ok=True)
        meta = dest / "snapshot.json"
        # store file blobs separately for large content
        blobs = dest / "files"
        blobs.mkdir(exist_ok=True)
        index = {}
        for rel, content in self._current.files.items():
            # Never store as .py — mypy must not treat snapshot blobs as modules.
            safe = rel.replace("/", "__") + ".blob"
            (blobs / safe).write_text(content, encoding="utf-8")
            index[rel] = safe
        meta.write_text(
            json.dumps(
                {
                    "iteration_id": self._current.iteration_id,
                    "created_at": self._current.created_at,
                    "branch_name": self._current.branch_name,
                    "index": index,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return meta

    def apply_writes(self, writes: dict[str, str]) -> list[str]:
        """Write new content; capture missing files as empty beforehand if needed."""
        assert self._current is not None
        changed: list[str] = []
        for rel, content in writes.items():
            if rel not in self._current.files:
                self.capture_before([rel])
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            changed.append(rel)
        return changed

    def rollback(self) -> SandboxResult:
        assert self._current is not None
        iid = self._current.iteration_id
        for rel, content in self._current.files.items():
            path = self.root / rel
            if content == "":
                if path.is_file():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return SandboxResult(ok=True, iteration_id=iid, rolled_back=True, detail="restored snapshot")

    def accept(self) -> SandboxResult:
        assert self._current is not None
        self.persist_snapshot()
        return SandboxResult(
            ok=True,
            iteration_id=self._current.iteration_id,
            rolled_back=False,
            detail="accepted; snapshot retained for audit",
            changed_paths=list(self._current.files.keys()),
        )
