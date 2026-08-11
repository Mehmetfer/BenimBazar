"""LEVEL 7 — Self-evolving research & governance layer (proposal-only).

Safe self-evolution loop:
  OBSERVE → HYPOTHESIZE → TEST → VALIDATE → PROPOSE → HUMAN APPROVAL

Never:
  - bypass RiskEngine / Kill Switch / Broker
  - auto-promote production models
  - rewrite production code or raise risk limits
  - invent market data

Builds on existing decision/, autonomous/, ai/, prediction/ packages.
"""

from __future__ import annotations

from level7.engine import Level7Engine, level7_report
from level7.autonomy_governor import AutonomyGovernor, AutonomyState

__all__ = [
    "AutonomyGovernor",
    "AutonomyState",
    "Level7Engine",
    "level7_report",
]
