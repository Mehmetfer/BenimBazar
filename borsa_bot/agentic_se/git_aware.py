"""Git-aware helpers — non-destructive inspection only."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GitSnapshot:
    branch: str
    status: str
    diff_stat: str
    dirty: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"UNKNOWN: {exc}"


def inspect_git(root: Path | None = None) -> GitSnapshot:
    # repo root may be parent of borsa_bot
    base = root or ROOT
    git_root = base if (base / ".git").exists() else base.parent
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], git_root).strip() or "UNKNOWN"
    status = _git(["status", "--short"], git_root)
    diff = _git(["diff", "--stat"], git_root)
    dirty = bool(status.strip()) and not status.startswith("UNKNOWN")
    return GitSnapshot(branch=branch, status=status[-2000:], diff_stat=diff[-2000:], dirty=dirty)
