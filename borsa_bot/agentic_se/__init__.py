"""Autonomous Software Engineering agent — agentic coding workflow (not trading).

User goal → understand → discover → decompose → plan → implement → test →
repair → regression → review → verify → deliver → learn.

Cannot: delete tests, bypass safety, unlock LIVE, loosen risk limits, or
weaken assertions to make failures pass.
"""

from __future__ import annotations

from agentic_se.engine import AutonomousSoftwareEngine, GoalRunReport
from agentic_se.scorecard import SEAutonomyScorecard, score_software_engineering_autonomy

__all__ = [
    "AutonomousSoftwareEngine",
    "GoalRunReport",
    "SEAutonomyScorecard",
    "score_software_engineering_autonomy",
]
