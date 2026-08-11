"""Recommended DB extensions for CRYPTO — Phase 1: documentation only.

Do NOT migrate or alter existing BIST tables in this phase.
Duplicate crypto database is forbidden; share paper.db / favorites when needed later.
"""

from __future__ import annotations

# Minimal future column (additive, nullable, default BIST):
#   ALTER TABLE … ADD COLUMN market_type TEXT NOT NULL DEFAULT 'BIST';
#
# Candidate tables (later phases, only when writing crypto rows):
#   - trades, positions, decision_log, predictions, favorites
#
# Isolation rule:
#   market_type='CRYPTO' rows must never enter BIST scan/score aggregates.
#   Queries that drive BIST TradingService stay market_type='BIST' OR NULL/default.

RECOMMENDED_MARKET_COLUMN = "market_type"
RECOMMENDED_DEFAULT = "BIST"
PHASE1_MIGRATION = False  # no schema change in Phase 1


def schema_recommendation() -> dict:
    return {
        "phase": 1,
        "migrate_now": False,
        "approach": "additive_nullable_or_default_BIST",
        "column": RECOMMENDED_MARKET_COLUMN,
        "default": RECOMMENDED_DEFAULT,
        "duplicate_database": False,
        "note": "Existing tables unchanged. Apply market_type only when crypto writes begin.",
    }
