"""Self-review pass — independent of implementer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_se.boundaries import FORBIDDEN_ACTIONS, se_path_allowed


@dataclass
class SEReview:
    approved: bool
    notes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_implementation(
    *,
    paths: list[str],
    diff_summary: str,
    has_tests: bool,
    weakened_assertions: bool = False,
    deleted_tests: bool = False,
) -> SEReview:
    blockers: list[str] = []
    notes: list[str] = []
    for p in paths:
        if not se_path_allowed(p):
            blockers.append(f"path not allowlisted: {p}")
    if not has_tests:
        blockers.append("missing tests")
    if weakened_assertions:
        blockers.append("assertion weakening forbidden")
    if deleted_tests:
        blockers.append("test deletion forbidden")
    for act in FORBIDDEN_ACTIONS:
        if act.replace("_", " ") in diff_summary.lower():
            blockers.append(f"forbidden action referenced: {act}")
    notes.extend(
        [
            "check edge cases",
            "preserve domain invariants",
            "prefer minimal reversible change",
        ]
    )
    return SEReview(approved=not blockers, notes=notes, blockers=blockers)
