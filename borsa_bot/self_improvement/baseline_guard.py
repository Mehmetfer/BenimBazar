"""Baseline protector — reject SI changes that shrink the pytest green count.

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
