"""Autonomous file discovery — search / inspect / test locations."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class DiscoveryResult:
    query: str
    code_hits: list[str] = field(default_factory=list)
    test_hits: list[str] = field(default_factory=list)
    config_hits: list[str] = field(default_factory=list)
    unknown: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_files(query: str, *, root: Path | None = None, limit: int = 40) -> DiscoveryResult:
    base = root or ROOT
    tokens = [t for t in re.split(r"[^a-zA-Z0-9_]+", query) if len(t) >= 3]
    if not tokens:
        return DiscoveryResult(query=query, unknown=True)
    code: list[str] = []
    tests: list[str] = []
    configs: list[str] = []
    skip = {".venv", "__pycache__", ".git", "node_modules", "snapshots"}
    pat = re.compile("|".join(re.escape(t) for t in tokens[:8]), re.I)

    for p in base.rglob("*"):
        if any(s in p.parts for s in skip):
            continue
        if not p.is_file():
            continue
        if p.suffix not in {".py", ".md", ".ini", ".toml", ".yml", ".yaml", ".env.example", ".json"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not pat.search(text) and not pat.search(p.name):
            continue
        rel = str(p.relative_to(base))
        if "tests" in p.parts or p.name.startswith("test_"):
            tests.append(rel)
        elif p.suffix in {".ini", ".toml", ".yml", ".yaml", ".env.example"} or "config" in rel:
            configs.append(rel)
        else:
            code.append(rel)
        if len(code) + len(tests) >= limit:
            break

    return DiscoveryResult(
        query=query,
        code_hits=sorted(set(code))[:limit],
        test_hits=sorted(set(tests))[:limit],
        config_hits=sorted(set(configs))[:20],
        unknown=not (code or tests),
    )
