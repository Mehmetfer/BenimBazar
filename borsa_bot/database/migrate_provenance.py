"""SQLite provenance column migrations — additive only, no data invention as LIVE."""

from __future__ import annotations

import sqlite3
from typing import Iterable


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # row[1] = name
    return {str(r[1]) for r in rows}


def ensure_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: Iterable[tuple[str, str]],
) -> list[str]:
    """ADD COLUMN if missing. Returns list of columns added."""
    existing = table_columns(conn, table)
    added: list[str] = []
    for name, typedef in columns:
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}")
        added.append(name)
    return added


def migrate_predictions_db(conn: sqlite3.Connection) -> dict:
    """Add provenance columns; historical priced rows → SIMULATED (only feed ever used)."""
    added = []
    added += ensure_columns(
        conn,
        "predictions",
        [
            ("market_data_source", "TEXT DEFAULT 'UNKNOWN'"),
            ("prediction_source", "TEXT DEFAULT 'UNKNOWN'"),
            ("data_source_kind", "TEXT DEFAULT 'UNKNOWN'"),
            ("market_type", "TEXT DEFAULT 'BIST'"),
        ],
    )
    added += ensure_columns(
        conn,
        "prediction_evaluations",
        [
            ("market_data_source", "TEXT DEFAULT 'UNKNOWN'"),
            ("actual_result_source", "TEXT DEFAULT 'UNKNOWN'"),
            ("data_source_kind", "TEXT DEFAULT 'UNKNOWN'"),
        ],
    )
    # Historical: never invent LIVE. Pre-provenance DB only ever had SimulatedProvider fills.
    conn.execute(
        """
        UPDATE predictions
        SET market_data_source='SIMULATED',
            prediction_source='SIMULATED',
            data_source_kind='SIMULATED'
        WHERE COALESCE(market_data_source, 'UNKNOWN') IN ('UNKNOWN', '')
          AND price_at_prediction IS NOT NULL
          AND price_at_prediction > 0
        """
    )
    conn.execute(
        """
        UPDATE predictions
        SET market_data_source=COALESCE(NULLIF(market_data_source, ''), 'UNKNOWN'),
            prediction_source=COALESCE(NULLIF(prediction_source, ''), 'UNKNOWN'),
            data_source_kind=COALESCE(NULLIF(data_source_kind, ''), 'UNKNOWN')
        WHERE market_data_source IS NULL OR prediction_source IS NULL OR data_source_kind IS NULL
           OR market_data_source='' OR prediction_source='' OR data_source_kind=''
        """
    )
    conn.execute(
        """
        UPDATE prediction_evaluations
        SET market_data_source='SIMULATED',
            actual_result_source='SIMULATED',
            data_source_kind='SIMULATED'
        WHERE COALESCE(market_data_source, 'UNKNOWN') IN ('UNKNOWN', '')
          AND actual_price IS NOT NULL
          AND actual_price > 0
        """
    )
    return {"added": added, "status": "PASS"}


def migrate_paper_db(conn: sqlite3.Connection) -> dict:
    added = []
    added += ensure_columns(
        conn,
        "decision_log",
        [("data_source_kind", "TEXT DEFAULT 'UNKNOWN'")],
    )
    added += ensure_columns(
        conn,
        "trades",
        [("data_source_kind", "TEXT DEFAULT 'UNKNOWN'")],
    )
    # Historical paper trades/decisions came from SimulatedProvider only
    conn.execute(
        """
        UPDATE decision_log
        SET data_source_kind='SIMULATED'
        WHERE COALESCE(data_source_kind, 'UNKNOWN') IN ('UNKNOWN', '')
          AND price IS NOT NULL AND price > 0
        """
    )
    conn.execute(
        """
        UPDATE trades
        SET data_source_kind='SIMULATED'
        WHERE COALESCE(data_source_kind, 'UNKNOWN') IN ('UNKNOWN', '')
          AND price IS NOT NULL AND price > 0
        """
    )
    return {"added": added, "status": "PASS"}
