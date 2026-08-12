"""Incremental repository understanding + architecture map."""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "agentic_se" / "data" / "codebase_memory.json"


@dataclass
class ModuleInfo:
    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepoMap:
    generated_at: str
    packages: list[str]
    entrypoints: list[str]
    test_dirs: list[str]
    critical_files: list[str]
    modules: list[ModuleInfo] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


CRITICAL_HINTS = (
    "risk/",
    "trading_safety/",
    "execution/",
    "decision/ade/",
    "self_improvement/",
    "agentic_se/",
    "autonomy/gates.py",
    "config/settings.py",
)


def _iter_py(root: Path) -> Iterable[Path]:
    skip = {".venv", "__pycache__", ".git", "node_modules", "mypy_stubs", "data", "snapshots"}
    for p in root.rglob("*.py"):
        if any(s in p.parts for s in skip):
            continue
        yield p


def discover_repository(root: Path | None = None, *, max_modules: int = 400) -> RepoMap:
    base = root or ROOT
    packages: set[str] = set()
    modules: list[ModuleInfo] = []
    entrypoints: list[str] = []
    tests: list[str] = []
    critical: list[str] = []

    for p in _iter_py(base):
        rel = str(p.relative_to(base))
        if p.name == "__init__.py":
            packages.add(str(p.parent.relative_to(base)))
        if p.name in {"main.py", "app.py", "run.py", "__main__.py"} or rel.endswith("/api.py"):
            entrypoints.append(rel)
        if "tests" in p.parts:
            tests.append(rel)
        if any(h in rel.replace("\\", "/") for h in CRITICAL_HINTS):
            critical.append(rel)
        if len(modules) < max_modules and "tests" not in p.parts:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            imports: list[str] = []
            for n in tree.body:
                if isinstance(n, ast.Import):
                    imports.extend(a.name for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module:
                    imports.append(n.module)
            modules.append(ModuleInfo(path=rel, classes=classes, functions=funcs, imports=imports[:30]))

    return RepoMap(
        generated_at=datetime.now(timezone.utc).isoformat(),
        packages=sorted(packages),
        entrypoints=sorted(set(entrypoints))[:40],
        test_dirs=sorted({str(Path(t).parent) for t in tests})[:80],
        critical_files=sorted(set(critical))[:120],
        modules=modules,
        invariants=[
            "unknown provider → BLOCK",
            "stale data → BLOCK",
            "kill switch → NO NEW ORDERS",
            "audit failure → BLOCK",
            "no test deletion",
            "LIVE default locked",
        ],
    )


def save_memory(repo: RepoMap, path: Path | None = None) -> Path:
    dest = path or MEMORY_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(repo.to_dict(), indent=2), encoding="utf-8")
    return dest


def load_memory(path: Path | None = None) -> dict[str, Any] | None:
    src = path or MEMORY_PATH
    if not src.is_file():
        return None
    return json.loads(src.read_text(encoding="utf-8"))


def invalidate_memory_for_paths(changed: list[str], path: Path | None = None) -> None:
    """Drop stale module entries for changed paths; force refresh on next discover."""
    mem = load_memory(path)
    if not mem:
        return
    changed_set = {c.replace("\\", "/") for c in changed}
    modules = [m for m in mem.get("modules", []) if m.get("path") not in changed_set]
    mem["modules"] = modules
    mem["generated_at"] = datetime.now(timezone.utc).isoformat()
    mem["stale_hint"] = True
    dest = path or MEMORY_PATH
    dest.write_text(json.dumps(mem, indent=2), encoding="utf-8")
