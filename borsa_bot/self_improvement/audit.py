"""Repository self-audit — find weaknesses with severity."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Finding:
    id: str
    title: str
    severity: Severity
    category: str
    path: str
    detail: str
    line: int | None = None
    suggested_priority: str = "Maintainability"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


PRIORITY_ORDER = [
    "Safety",
    "Correctness",
    "Reliability",
    "Recovery",
    "Performance",
    "Maintainability",
    "Feature",
]


def _iter_py(base: Path | None = None) -> Iterable[Path]:
    root = base or ROOT
    skip = {".venv", "__pycache__", ".git", "node_modules", "mypy_stubs"}
    for p in root.rglob("*.py"):
        if any(s in p.parts for s in skip):
            continue
        yield p


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def audit_repository(*, root: Path | None = None, max_findings: int = 200) -> list[Finding]:
    """Scan codebase for TODO/FIXME, bare except, missing tests signals, etc."""
    base = root or ROOT
    findings: list[Finding] = []
    n = 0

    todo_re = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
    bare_except_re = re.compile(r"except\s*:")
    pass_re = re.compile(r"^\s*pass\s*(#.*)?$")

    for p in _iter_py(base):
        if n >= max_findings:
            break
        rel = _rel(p)
        text = p.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        for i, line in enumerate(lines, 1):
            if n >= max_findings:
                break
            m = todo_re.search(line)
            if m:
                sev = Severity.HIGH if m.group(1) == "FIXME" else Severity.MEDIUM
                findings.append(
                    Finding(
                        id=f"F-{n+1:04d}",
                        title=f"{m.group(1)} marker",
                        severity=sev,
                        category="incomplete",
                        path=rel,
                        detail=line.strip()[:200],
                        line=i,
                        suggested_priority="Correctness" if sev is Severity.HIGH else "Maintainability",
                    )
                )
                n += 1

            if bare_except_re.search(line) and "except Exception" not in line and "except BaseException" not in line:
                findings.append(
                    Finding(
                        id=f"F-{n+1:04d}",
                        title="Bare except",
                        severity=Severity.HIGH,
                        category="weak_error_handling",
                        path=rel,
                        detail=line.strip()[:200],
                        line=i,
                        suggested_priority="Reliability",
                    )
                )
                n += 1

        # AST complexity / empty handlers
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    id=f"F-{n+1:04d}",
                    title="SyntaxError — CRITICAL",
                    severity=Severity.CRITICAL,
                    category="correctness",
                    path=rel,
                    detail=str(exc),
                    line=getattr(exc, "lineno", None),
                    suggested_priority="Correctness",
                )
            )
            n += 1
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body_len = len(node.body)
                if body_len > 80:
                    findings.append(
                        Finding(
                            id=f"F-{n+1:04d}",
                            title=f"High complexity function {node.name}",
                            severity=Severity.MEDIUM,
                            category="complexity",
                            path=rel,
                            detail=f"{node.name} has {body_len} body stmts",
                            line=getattr(node, "lineno", None),
                            suggested_priority="Maintainability",
                        )
                    )
                    n += 1
                    if n >= max_findings:
                        break

    # Missing test for self_improvement package itself (bootstrap awareness)
    si_dir = base / "self_improvement"
    test_si = base / "tests" / "test_self_improvement.py"
    if si_dir.is_dir() and not test_si.is_file():
        findings.append(
            Finding(
                id=f"F-{n+1:04d}",
                title="self_improvement package lacks dedicated tests",
                severity=Severity.HIGH,
                category="missing_tests",
                path="self_improvement/",
                detail="No tests/test_self_improvement.py",
                suggested_priority="Correctness",
            )
        )

    # Domain invariant file presence check
    inv = base / "tests" / "test_domain_invariants.py"
    if not inv.is_file():
        findings.append(
            Finding(
                id=f"F-{n+1:04d}",
                title="Missing domain invariant tests",
                severity=Severity.CRITICAL,
                category="domain_invariant",
                path="tests/",
                detail="test_domain_invariants.py missing",
                suggested_priority="Safety",
            )
        )

    return findings


def findings_by_priority(findings: list[Finding]) -> list[Finding]:
    pri = {p: i for i, p in enumerate(PRIORITY_ORDER)}
    sev_rank = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}

    def key(f: Finding) -> tuple[int, int, str]:
        return (pri.get(f.suggested_priority, 99), sev_rank.get(f.severity, 9), f.id)

    return sorted(findings, key=key)
