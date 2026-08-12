"""Playground module for ASE benchmarks — intentionally simple, allowlisted.

BUGGY_ADD is fixed by the agent during the bugfix benchmark.
Do not use in production trading paths.
"""

from __future__ import annotations


def buggy_add(a: int, b: int) -> int:
    """Return a+b. Benchmark may inject a wrong implementation."""
    return a + b


def clamp_non_negative(x: int) -> int:
    """Return max(0, x)."""
    return x if x >= 0 else 0
