"""Versioned category compatibility — not hard-coded business rules in callers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import COMPATIBILITY_POLICY_VERSION, KNOWN_CATEGORIES


@dataclass(frozen=True)
class CompatibilityEdge:
    source_category: str
    target_category: str
    weight: float = 1.0
    note: str = ""


# Default matrix: same-category edges only. Admin/config can extend later.
# Examples like AUTO→MOTORCYCLE are NOT assumed as business truth.
_DEFAULT_EDGES: tuple[CompatibilityEdge, ...] = tuple(
    CompatibilityEdge(c, c, 1.0, "same-category") for c in KNOWN_CATEGORIES
)


class CategoryCompatibility:
    def __init__(
        self,
        edges: tuple[CompatibilityEdge, ...] | None = None,
        *,
        policy_version: str = COMPATIBILITY_POLICY_VERSION,
    ):
        self.policy_version = policy_version
        self._edges = edges if edges is not None else _DEFAULT_EDGES
        self._index: dict[tuple[str, str], CompatibilityEdge] = {
            (e.source_category.lower(), e.target_category.lower()): e for e in self._edges
        }

    def compatible(self, have_category: str, want_category: str) -> bool:
        return self.score(have_category, want_category) > 0

    def score(self, have_category: str, want_category: str) -> float:
        if not have_category or not want_category:
            return 0.0
        key = (have_category.strip().lower(), want_category.strip().lower())
        edge = self._index.get(key)
        return float(edge.weight) if edge else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "edges": [
                {
                    "source": e.source_category,
                    "target": e.target_category,
                    "weight": e.weight,
                    "note": e.note,
                }
                for e in self._edges
            ],
        }


_DEFAULT = CategoryCompatibility()


def get_compatibility() -> CategoryCompatibility:
    return _DEFAULT
