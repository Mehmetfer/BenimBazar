"""Autonomy development protocol — measurable gates, lessons, self-review.

Research / paper / shadow only. Never unlocks LIVE broker.
Does NOT self-modify production trading code.
"""

from __future__ import annotations

from autonomy.scorecard import AutonomyScorecard, score_autonomy
from autonomy.levels import LevelStatus, evaluate_levels

__all__ = [
    "AutonomyScorecard",
    "LevelStatus",
    "evaluate_levels",
    "score_autonomy",
]
