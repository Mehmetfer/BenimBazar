"""Safe auto-implementations for allowlisted improvements."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from self_improvement.backlog import ImprovementItem
from self_improvement.invariants import SafetyViolation, assert_invariant_untouched, path_allowed_for_auto_impl

ROOT = Path(__file__).resolve().parents[1]

ImplementFn = Callable[[ImprovementItem], dict[str, str]]


def implement_baseline_guard(_item: ImprovementItem) -> dict[str, str]:
    """Create baseline protector module + ensure data dir README."""
    content = '''"""Baseline protector — reject SI changes that shrink the pytest green count.

Deleting tests to raise scores is forbidden.
"""

from __future__ import annotations

from self_improvement.verify import load_baseline, parse_pytest_summary, save_baseline


def assert_baseline_not_regressed(pytest_output: str, *, baseline_passed: int | None = None) -> None:
    passed, failed = parse_pytest_summary(pytest_output)
    base = baseline_passed if baseline_passed is not None else int(load_baseline().get("passed", 0))
    if failed > 0:
        raise AssertionError(f"tests failed={failed}; SI change rejected")
    if base > 0 and passed < base:
        raise AssertionError(
            f"baseline regression: passed {base} → {passed}. "
            "Test deletion or breakage is forbidden."
        )


def record_new_baseline(passed: int, failed: int = 0, note: str = "si-accepted") -> None:
    if failed != 0:
        raise AssertionError("cannot record baseline with failures")
    prev = int(load_baseline().get("passed", 0))
    if prev > 0 and passed < prev:
        raise AssertionError("refusing to lower recorded baseline")
    save_baseline(passed=passed, failed=failed, note=note)
'''
    readme = (
        "# Self-improvement data\n\n"
        "Snapshots, backlog, attempts, and baseline JSON live here.\n"
        "Not a LIVE trading store. SI must not delete audit/test evidence.\n"
    )
    return {
        "self_improvement/baseline_guard.py": content,
        "self_improvement/data/README.md": readme,
    }


def implement_si_health_module(_item: ImprovementItem) -> dict[str, str]:
    content = '''"""Repository health snapshot for SI observe phase."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class HealthSnapshot:
    generated_at: str
    py_files: int
    test_files: int
    has_domain_invariants: bool
    has_trading_safety: bool
    has_ade: bool
    live_broker_locked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe_health(root: Path | None = None) -> HealthSnapshot:
    base = root or ROOT
    py = list(base.rglob("*.py"))
    tests = [p for p in py if "tests" in p.parts and p.name.startswith("test_")]
    return HealthSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        py_files=len(py),
        test_files=len(tests),
        has_domain_invariants=(base / "tests" / "test_domain_invariants.py").is_file(),
        has_trading_safety=(base / "trading_safety").is_dir(),
        has_ade=(base / "decision" / "ade").is_dir(),
        live_broker_locked=True,  # SI never unlocks; report locked
    )
'''
    return {"self_improvement/health.py": content}


REGISTRY: dict[str, ImplementFn] = {
    "baseline_guard": implement_baseline_guard,
    "si_health": implement_si_health_module,
}


def select_implementer(item: ImprovementItem) -> ImplementFn | None:
    title = item.title.lower()
    cat = item.category.lower()
    if "baseline" in title or "baseline" in item.notes.lower():
        return implement_baseline_guard
    if "missing_tests" in cat or "self_improvement" in title.lower():
        # Prefer health+tests via engine; health module alone here
        return implement_si_health_module
    if "todo" in title.lower() or "fixme" in title.lower():
        return None  # do not auto-delete TODOs without human
    return None


def build_writes(item: ImprovementItem, fn: ImplementFn) -> dict[str, str]:
    writes = fn(item)
    for path in writes:
        if not path_allowed_for_auto_impl(path):
            raise SafetyViolation(f"implementer produced non-allowlisted path: {path}")
    assert_invariant_untouched(writes)
    return writes
