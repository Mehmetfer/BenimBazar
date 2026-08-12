"""FAZ 2 — Repo-wide completeness: who calls this symbol / surface gaps."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CompletenessReport:
    symbol: str
    definition_files: list[str] = field(default_factory=list)
    call_sites: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_mentions: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iter_py(base: Path | None = None) -> Iterable[Path]:
    root = base or ROOT
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        yield p


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def scan_symbol(symbol: str) -> CompletenessReport:
    """Answer: where is this defined, called, tested, configured?"""
    defs: list[str] = []
    calls: list[str] = []
    tests: list[str] = []
    configs: list[str] = []
    pat = re.compile(rf"\b{re.escape(symbol)}\b")

    for p in _iter_py():
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not pat.search(text):
            continue
        rel = _rel(p)
        if rel.startswith("tests/") or "/tests/" in rel:
            tests.append(rel)
        else:
            calls.append(rel)
        # crude def detection
        if re.search(rf"^\s*(def|class)\s+{re.escape(symbol)}\b", text, re.M):
            defs.append(rel)

    for name in (".env.example", "README.md", "PROJECT_AUDIT.md"):
        fp = ROOT / name
        if fp.is_file() and symbol in fp.read_text(encoding="utf-8", errors="ignore"):
            configs.append(name)

    gaps: list[str] = []
    if not defs and not calls:
        gaps.append("symbol not found in repo")
    if calls and not tests:
        gaps.append("no test file mentions this symbol")
    if defs and len(calls) <= len(defs):
        # only defined, maybe unused — soft gap
        if len(calls) == len(defs):
            gaps.append("possibly unused outside definition file(s)")

    return CompletenessReport(
        symbol=symbol,
        definition_files=sorted(set(defs)),
        call_sites=sorted(set(calls)),
        test_files=sorted(set(tests)),
        config_mentions=sorted(set(configs)),
        gaps=gaps,
        ok="symbol not found in repo" not in gaps,
    )


def scan_changed_exports(paths: list[str | Path]) -> list[CompletenessReport]:
    """For each def/class in changed files, scan call sites."""
    reports: list[CompletenessReport] = []
    for raw in paths:
        p = Path(raw) if Path(raw).is_absolute() else ROOT / raw
        if not p.is_file() or p.suffix != ".py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith("_"):
                    continue
                reports.append(scan_symbol(node.name))
    return reports


def bist_crypto_isolation_check() -> dict[str, Any]:
    """Detect obvious BIST/CRYPTO mixing smells in crypto package."""
    smells: list[str] = []
    crypto_root = ROOT / "crypto"
    if crypto_root.is_dir():
        for p in crypto_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "TradingService" in text and "BIST" in text and "isolated" not in text.lower():
                # soft — many files mention isolation intentionally
                pass
            if "normalize_app_symbol" in text and "normalize_crypto" not in text:
                if "stamp_" in text:
                    smells.append(f"{_rel(p)}: uses BIST normalize_app_symbol near stamp (verify crypto OK)")
    return {
        "ok": True,  # advisory
        "smells": smells,
        "note": "advisory isolation scan — not a hard fail",
    }
