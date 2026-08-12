"""FAZ 7 — Autonomous work loop definition (enforced by runner + tests)."""

from __future__ import annotations

LOOP_STEPS = [
    "PLAN",
    "IMPLEMENT",
    "SELF-REVIEW",
    "TEST",
    "FAILURE ANALYSIS",
    "PATCH",
    "REGRESSION TEST",
    "RE-RUN",
    "COMPLETENESS SCAN",
    "FINAL VALIDATION",
    "REPORT",
]


def loop_complete(completed: list[str]) -> bool:
    """Task is not done until all steps are marked complete."""
    need = set(LOOP_STEPS)
    have = {s.strip().upper() for s in completed}
    # allow hyphen/space variants
    normalized = set()
    for h in have:
        normalized.add(h.replace("_", " ").replace("-", " "))
    need_n = {s.replace("-", " ") for s in need}
    return need_n.issubset(normalized)
