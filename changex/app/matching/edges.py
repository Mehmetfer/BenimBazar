"""Internal directed graph edge model — not persisted as a full edge table."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .config import CHAIN_ENGINE_VERSION, MATCHING_POLICY_VERSION
from .scoring import ScoreBreakdown


@dataclass
class GraphEdge:
    source_listing_id: int
    target_listing_id: int
    owner_id: int
    target_owner_id: int
    score: float
    score_breakdown: ScoreBreakdown
    reason: str
    created_at: float = field(default_factory=time.time)
    policy_version: str = MATCHING_POLICY_VERSION
    engine_version: str = CHAIN_ENGINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_listing_id": self.source_listing_id,
            "target_listing_id": self.target_listing_id,
            "owner_id": self.owner_id,
            "target_owner_id": self.target_owner_id,
            "score": self.score,
            "score_breakdown": self.score_breakdown.to_dict(),
            "reason": self.reason,
            "created_at": self.created_at,
            "policy_version": self.policy_version,
            "engine_version": self.engine_version,
            "graph_edge_materialized": False,
        }
