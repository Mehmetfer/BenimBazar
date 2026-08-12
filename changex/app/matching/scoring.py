"""Scoring contract + MatchCandidate model — no automatic matching yet."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import CHAIN_ENGINE_VERSION, MATCHING_POLICY_VERSION


@dataclass
class ScoreBreakdown:
    """Deterministic domain scores — separate from any future AI suggestion."""

    category_score: float = 0.0
    value_score: float = 0.0
    want_score: float = 0.0
    location_score: float = 0.0
    condition_score: float = 0.0
    preference_score: float = 0.0

    @property
    def total_score(self) -> float:
        # Equal weights for contract clarity; production may reweight later.
        parts = [
            self.category_score,
            self.value_score,
            self.want_score,
            self.location_score,
            self.condition_score,
            self.preference_score,
        ]
        return sum(parts) / len(parts)

    def to_dict(self) -> dict[str, float]:
        return {
            "category_score": self.category_score,
            "value_score": self.value_score,
            "want_score": self.want_score,
            "location_score": self.location_score,
            "condition_score": self.condition_score,
            "preference_score": self.preference_score,
            "total_score": self.total_score,
        }


class ScoreProvider(Protocol):
    """Interface for future deterministic scorers (not AI sole authority)."""

    def score_pair(self, source: dict[str, Any], target: dict[str, Any]) -> ScoreBreakdown: ...


@dataclass
class MatchCandidate:
    """Directed edge A→B: A's WANT compatible with B's HAVE (future graph edge)."""

    source_listing_id: int
    target_listing_id: int
    scores: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    policy_version: str = MATCHING_POLICY_VERSION
    eligible: bool = False
    rejection_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_listing": self.source_listing_id,
            "target_listing": self.target_listing_id,
            "category_score": self.scores.category_score,
            "value_score": self.scores.value_score,
            "want_score": self.scores.want_score,
            "location_score": self.scores.location_score,
            "condition_score": self.scores.condition_score,
            "total_score": self.scores.total_score,
            "policy_version": self.policy_version,
            "eligible": self.eligible,
            "rejection_reasons": self.rejection_reasons,
            # Edges are computed on-demand; full edge table is not persisted
            "graph_edge_materialized": False,
            "chain_algorithm": CHAIN_ENGINE_VERSION,
        }


class NullScoreProvider:
    """Placeholder scorer — returns zeros; real matching not enabled."""

    def score_pair(self, source: dict[str, Any], target: dict[str, Any]) -> ScoreBreakdown:
        return ScoreBreakdown()
