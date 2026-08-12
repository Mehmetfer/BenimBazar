"""FAZ 1 — Self-review engine: second pass over changed code before claiming success."""

from __future__ import annotations

import ast
import py_compile
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]  # borsa_bot/


@dataclass
class ReviewFinding:
    severity: str  # error | warn | info
    code: str
    message: str
    path: str = ""


@dataclass
class SelfReviewReport:
    ok: bool
    findings: list[ReviewFinding] = field(default_factory=list)
    files_reviewed: list[str] = field(default_factory=list)
    gates_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "files_reviewed": self.files_reviewed,
            "gates_run": self.gates_run,
            "findings": [asdict(f) for f in self.findings],
            "error_count": sum(1 for f in self.findings if f.severity == "error"),
            "warn_count": sum(1 for f in self.findings if f.severity == "warn"),
        }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_syntax(paths: Iterable[Path]) -> list[ReviewFinding]:
    out: list[ReviewFinding] = []
    for p in paths:
        if p.suffix != ".py" or not p.is_file():
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as exc:
            out.append(ReviewFinding("error", "SYNTAX", str(exc), _rel(p)))
    return out


def check_imports_ast(paths: Iterable[Path]) -> list[ReviewFinding]:
    """Parse imports; flag relative empties / obvious bad syntax only (no network)."""
    out: list[ReviewFinding] = []
    for p in paths:
        if p.suffix != ".py" or not p.is_file():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as exc:
            out.append(ReviewFinding("error", "AST", f"syntax: {exc}", _rel(p)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is None and node.level == 0:
                out.append(ReviewFinding("warn", "IMPORT", "empty ImportFrom", _rel(p)))
    return out


def find_call_sites(symbol: str, *, under: Path | None = None) -> list[str]:
    """Repo-wide text scan for symbol usages (completeness aid)."""
    base = under or ROOT
    hits: list[str] = []
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts or "venv" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if symbol in text:
            hits.append(_rel(p))
    return sorted(set(hits))


def check_live_broker_not_unlocked(paths: Iterable[Path]) -> list[ReviewFinding]:
    """Refuse patches that enable LIVE broker in code/defaults."""
    out: list[ReviewFinding] = []
    # Build patterns at runtime so this detector file does not self-match.
    tok = "LIVE_BROKER_" + "ENABLED"
    banned = (
        tok + '", True',
        tok + "', True",
        "live_broker_enabled: bool = " + "True",
        "live_broker_enabled = " + "True",
    )
    for p in paths:
        if p.suffix != ".py" or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for b in banned:
            if b in text:
                out.append(
                    ReviewFinding(
                        "error",
                        "LIVE_LOCK",
                        f"refuses LIVE unlock pattern: {b}",
                        _rel(p),
                    )
                )
    return out


def run_pytest_nodes(nodes: list[str], *, timeout_sec: int = 120) -> tuple[bool, str]:
    if not nodes:
        return True, "no nodes"
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=line", *nodes]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
        )
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    ok = proc.returncode == 0
    tail = (proc.stdout or "")[-2000:] + "\n" + (proc.stderr or "")[-1000:]
    return ok, tail


def self_review(
    paths: Sequence[str | Path],
    *,
    related_tests: list[str] | None = None,
    run_tests: bool = True,
) -> SelfReviewReport:
    """Second-pass review. Task is not successful until report.ok is True."""
    resolved = [Path(p) if Path(p).is_absolute() else ROOT / p for p in paths]
    resolved = [p for p in resolved if p.exists()]
    findings: list[ReviewFinding] = []
    gates: list[str] = []

    findings.extend(check_syntax(resolved))
    gates.append("syntax")
    findings.extend(check_imports_ast(resolved))
    gates.append("imports_ast")
    findings.extend(check_live_broker_not_unlocked(resolved))
    gates.append("live_lock")

    # Edge: empty change set
    if not resolved:
        findings.append(ReviewFinding("warn", "EMPTY", "no files to review"))

    if run_tests and related_tests:
        ok, log = run_pytest_nodes(related_tests)
        gates.append("related_tests")
        if not ok:
            findings.append(ReviewFinding("error", "TEST", f"related tests failed:\n{log[-1500:]}"))

    errors = [f for f in findings if f.severity == "error"]
    return SelfReviewReport(
        ok=len(errors) == 0,
        findings=findings,
        files_reviewed=[_rel(p) for p in resolved],
        gates_run=gates,
    )
