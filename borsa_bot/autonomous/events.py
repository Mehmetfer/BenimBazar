"""Autonomous event log — audit-critical trading lifecycle events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT


class AutonomyEventType:
    SCAN_STARTED = "SCAN_STARTED"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SIGNAL_CREATED = "SIGNAL_CREATED"
    TRADE_PLAN_CREATED = "TRADE_PLAN_CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_BLOCKED = "ORDER_BLOCKED"
    SHADOW_INTENT = "SHADOW_INTENT"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    KILL_SWITCH = "KILL_SWITCH"
    HEALTH_FAIL = "HEALTH_FAIL"
    RECONCILE_FAIL = "RECONCILE_FAIL"
    CYCLE_BLOCKED = "CYCLE_BLOCKED"
    GATE_FAIL = "GATE_FAIL"


class AutonomyEventLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "autonomy_events.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    cycle_id TEXT,
                    market TEXT,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    payload_json TEXT
                )
                """
            )

    def emit(
        self,
        event_type: str,
        *,
        cycle_id: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO autonomy_events(ts, cycle_id, market, event_type, symbol, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now().isoformat(),
                    cycle_id,
                    market,
                    event_type,
                    symbol,
                    json.dumps(payload or {}),
                ),
            )

    def recent(self, limit: int = 100, cycle_id: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as c:
            if cycle_id:
                rows = c.execute(
                    "SELECT * FROM autonomy_events WHERE cycle_id=? ORDER BY id DESC LIMIT ?",
                    (cycle_id, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM autonomy_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                d["payload"] = {}
            out.append(d)
        return out
