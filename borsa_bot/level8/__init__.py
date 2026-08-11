"""LEVEL 8 — Continuous Autonomous Research & Learning Engine.

Reuses Level 7 (hypothesis/experiment/lab/memory/outcome). Adds:
  continuous loop, decision snapshots/replay, drift, experiment factory,
  knowledge memory, periodic reports, research budget, promotion scoring.

Governance (immutable):
  learning authority = HIGH
  production mutate = RESTRICTED (propose only)
  risk limits / kill switch / broker permissions = DENIED
"""

from __future__ import annotations

from level8.engine import ContinuousLearningEngine, level8_report

__all__ = ["ContinuousLearningEngine", "level8_report"]
