"""FAZ 4 — Test gates. Any failure → STOP → ANALYZE → PATCH → TEST AGAIN."""

from __future__ import annotations

import py_compile
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autonomy.lessons import required_regression_tests, seed_known_lessons
from autonomy.self_review import self_review

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GateResult:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateSuiteResult:
    ok: bool
    gates: list[GateResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "gates": [g.to_dict() for g in self.gates]}


def _pytest(nodes: list[str], timeout: int = 180) -> GateResult:
    if not nodes:
        return GateResult("pytest", True, "skipped: empty")
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=line", *nodes]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    ok = proc.returncode == 0
    detail = ((proc.stdout or "") + (proc.stderr or ""))[-2500:]
    return GateResult("pytest:" + ",".join(nodes[:3]), ok, detail)


def run_gates(
    *,
    changed_files: list[str] | None = None,
    unit_nodes: list[str] | None = None,
    integration_nodes: list[str] | None = None,
    smoke_nodes: list[str] | None = None,
    run_full_regression: bool = True,
) -> GateSuiteResult:
    """Gates 1–8. Fail-closed: any error → ok=False."""
    seed_known_lessons()
    results: list[GateResult] = []
    files = [ROOT / f if not Path(f).is_absolute() else Path(f) for f in (changed_files or [])]

    # Gate 1 — syntax / import compile
    syn_ok = True
    syn_detail = []
    targets = files or [ROOT / "autonomy"]
    for t in targets:
        paths = [t] if t.is_file() else list(t.rglob("*.py"))
        for p in paths:
            if p.suffix != ".py" or "__pycache__" in p.parts:
                continue
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                syn_ok = False
                syn_detail.append(str(exc))
    results.append(GateResult("G1_syntax_import", syn_ok, "; ".join(syn_detail) or "ok"))

    # Gate 2 — lint (optional: use ruff/flake if present; else ast parse)
    lint_ok = True
    try:
        import ast

        for t in targets:
            paths = [t] if t.is_file() else list(t.rglob("*.py"))
            for p in paths:
                if p.suffix != ".py" or "__pycache__" in p.parts:
                    continue
                ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError as exc:
        lint_ok = False
        results.append(GateResult("G2_lint", False, str(exc)))
    else:
        results.append(GateResult("G2_lint", lint_ok, "ast-parse ok (ruff not required)"))

    # Gate 3 — HARD typecheck (scoped critical modules). Soft-pass forbidden.
    results.append(run_g3_typecheck())

    # Gate 4 — unit
    unit = unit_nodes or [
        "tests/test_autonomy_protocol.py",
        "tests/test_core.py",
    ]
    existing_u = [n for n in unit if (ROOT / n.split("::")[0]).exists()]
    results.append(_rename(_pytest(existing_u), "G4_unit"))

    # Gate 5 — integration (level gates + crypto foundation)
    integ = integration_nodes or [
        "tests/test_level_gates.py",
        "tests/test_crypto_foundation.py",
        "tests/test_data_source_isolation.py",
    ]
    existing = [n for n in integ if (ROOT / n.split("::")[0]).exists()]
    results.append(_rename(_pytest(existing, timeout=180), "G5_integration"))

    # Gate 6 — regression from lesson store
    if run_full_regression:
        regs = required_regression_tests()
        existing_r = []
        for n in regs:
            path = n.split("::")[0]
            if (ROOT / path).exists():
                existing_r.append(n)
        results.append(_rename(_pytest(existing_r, timeout=180), "G6_regression"))
    else:
        results.append(GateResult("G6_regression", True, "skipped"))

    # Gate 7 — smoke
    smoke = smoke_nodes or [
        "tests/test_level_gates.py::test_l1_app_imports_and_settings",
        "tests/test_level_gates.py::test_l6_live_broker_locked",
        "tests/test_level8.py",
    ]
    existing_s = [n for n in smoke if (ROOT / n.split("::")[0]).exists()]
    results.append(_rename(_pytest(existing_s, timeout=120), "G7_smoke"))

    # Gate 8 — self-review
    review_paths = [str(f.relative_to(ROOT)) if f.is_absolute() else str(f) for f in (files or [ROOT / "autonomy" / "lessons.py"])]
    # normalize
    norm = []
    for rp in review_paths:
        p = Path(rp)
        if not p.is_absolute():
            p = ROOT / rp
        if p.is_dir():
            norm.extend([str(x.relative_to(ROOT)) for x in p.rglob("*.py")])
        elif p.exists():
            norm.append(str(Path(rp)))
    rev = self_review(norm or ["autonomy/lessons.py"], related_tests=None, run_tests=False)
    results.append(GateResult("G8_self_review", rev.ok, str(rev.to_dict())[:1500]))

    ok = all(g.ok for g in results)
    return GateSuiteResult(ok=ok, gates=results)


def _rename(g: GateResult, name: str) -> GateResult:
    return GateResult(name=name, ok=g.ok, detail=g.detail)


G3_TARGETS = [
    "autonomy",
    "crypto/providers/factory.py",
    "crypto/safety.py",
    "crypto/reliability.py",
    "execution/safety.py",
    "autonomous/gates.py",
    "autonomous/governors.py",
]


def run_g3_typecheck() -> GateResult:
    """HARD gate: mypy must be installed and scoped critical modules must pass."""
    mypy = subprocess.run(
        [sys.executable, "-m", "mypy", "--version"],
        capture_output=True,
        text=True,
    )
    if mypy.returncode != 0:
        return GateResult(
            "G3_typecheck",
            False,
            "HARD FAIL: mypy not installed — soft-pass forbidden",
        )
    cfg = ROOT / "mypy.ini"
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        *G3_TARGETS,
        "--config-file",
        str(cfg) if cfg.is_file() else "mypy.ini",
    ]
    tc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    detail = ((tc.stdout or "") + "\n" + (tc.stderr or ""))[-2000:]
    if tc.returncode != 0:
        return GateResult("G3_typecheck", False, f"HARD FAIL mypy:\n{detail}")
    return GateResult(
        "G3_typecheck",
        True,
        f"mypy PASS scoped targets={G3_TARGETS}\n{detail}",
    )
