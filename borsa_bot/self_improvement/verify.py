"""Verification: baseline lock, gates, regression compare."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "self_improvement" / "data" / "baseline.json"


@dataclass
class VerifyResult:
    ok: bool
    passed: int
    failed: int
    baseline_passed: int
    regression: bool
    detail: str = ""
    gates: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_baseline() -> dict[str, Any]:
    if BASELINE_PATH.is_file():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"passed": 0, "failed": 0, "note": "unset"}


def save_baseline(*, passed: int, failed: int, note: str = "") -> Path:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"passed": passed, "failed": failed, "note": note}
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return BASELINE_PATH


def parse_pytest_summary(output: str) -> tuple[int, int]:
    """Parse 'N passed' and 'M failed' from pytest -q summary."""
    passed = 0
    failed = 0
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    if "error" in output.lower() and failed == 0:
        em = re.search(r"(\d+)\s+error", output)
        if em:
            failed = int(em.group(1))
    return passed, failed


def run_pytest(nodes: list[str] | None = None, *, timeout: int = 300) -> tuple[bool, int, int, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=line"]
    if nodes:
        cmd.extend(nodes)
    else:
        cmd.append("tests/")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    passed, failed = parse_pytest_summary(out)
    return proc.returncode == 0, passed, failed, out[-4000:]


def run_mypy_scoped(paths: list[str], *, timeout: int = 120) -> tuple[bool, str]:
    if not paths:
        return True, "skipped"
    if not (ROOT / "mypy.ini").is_file():
        return True, "mypy.ini missing — skipped"

    expanded: list[str] = []
    skip_parts = {"data", "snapshots", "__pycache__"}
    for raw in paths:
        p = ROOT / raw if not Path(raw).is_absolute() else Path(raw)
        if p.is_file() and p.suffix == ".py":
            expanded.append(str(p))
            continue
        if p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if any(s in f.parts for s in skip_parts):
                    continue
                # Ignore snapshot blobs accidentally named *.py under data/
                if "self_improvement" in f.parts and "data" in f.parts:
                    continue
                expanded.append(str(f))
    if not expanded:
        return True, "no py files"
    cmd = [sys.executable, "-m", "mypy", "--config-file", "mypy.ini", *expanded]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out[-2000:]


def verify_against_baseline(
    *,
    nodes: list[str] | None = None,
    mypy_paths: list[str] | None = None,
    expanded: bool = False,
) -> VerifyResult:
    baseline = load_baseline()
    base_passed = int(baseline.get("passed", 0))
    test_nodes = None if expanded else (nodes or ["tests/test_self_improvement.py"])
    if expanded:
        test_nodes = None  # full suite

    ok, passed, failed, detail = run_pytest(test_nodes)
    mypy_ok, mypy_detail = run_mypy_scoped(mypy_paths or ["self_improvement"])
    # Regression: fewer passed than baseline when full suite, or any failed
    regression = failed > 0 or (expanded and base_passed > 0 and passed < base_passed)
    # Test deletion heuristic: if full suite and passed drops by >0 vs baseline
    if expanded and base_passed > 0 and passed < base_passed:
        regression = True
        detail = f"BASELINE REGRESSION: {base_passed} → {passed}\n" + detail

    all_ok = ok and mypy_ok and not regression and failed == 0
    return VerifyResult(
        ok=all_ok,
        passed=passed,
        failed=failed,
        baseline_passed=base_passed,
        regression=regression,
        detail=detail + ("\n" + mypy_detail if mypy_detail else ""),
        gates={"pytest": ok and failed == 0, "mypy": mypy_ok, "baseline": not regression},
    )
