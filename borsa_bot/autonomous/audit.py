"""Autonomous cycle audit log — answers 'why no trade?'."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT


def make_idempotency_key(
    market: str,
    symbol: str,
    signal: str,
    *,
    window_minutes: int = 15,
    when: datetime | None = None,
) -> str:
    """market+symbol+signal+time-window bucket for duplicate order protection."""
    ts = when or datetime.now(timezone.utc)
    bucket = int(ts.timestamp() // max(60, window_minutes * 60))
    return f"{market.upper()}|{symbol.upper()}|{signal.upper()}|{bucket}"


class AutonomyAuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "autonomy_audit.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS autonomy_cycles (
                    cycle_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    market TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    kill_switch INTEGER DEFAULT 0,
                    filter_json TEXT,
                    summary_json TEXT,
                    note TEXT
                );
                CREATE TABLE IF NOT EXISTS autonomy_symbol_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    data_source TEXT,
                    data_quality TEXT,
                    regime TEXT,
                    model_score REAL,
                    signal TEXT,
                    risk_result TEXT,
                    trade_plan_json TEXT,
                    execution_result TEXT,
                    prediction_id TEXT,
                    explain_json TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS autonomy_order_keys (
                    dedupe_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    order_id TEXT
                );
                """
            )

    def new_cycle_id(self) -> str:
        return f"CYC-{uuid.uuid4().hex[:12]}"

    def write_cycle(
        self,
        *,
        cycle_id: str,
        market: str,
        mode: str,
        kill_switch: bool,
        filter_info: dict | None,
        summary: dict | None,
        note: str = "",
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO autonomy_cycles(cycle_id, timestamp, market, mode, kill_switch, filter_json, summary_json, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    utc_now().isoformat(),
                    market,
                    mode,
                    1 if kill_switch else 0,
                    json.dumps(filter_info or {}),
                    json.dumps(summary or {}),
                    note,
                ),
            )

    def write_symbol_event(self, cycle_id: str, market: str, row: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO autonomy_symbol_events(
                    cycle_id, timestamp, market, symbol, data_source, data_quality, regime,
                    model_score, signal, risk_result, trade_plan_json, execution_result,
                    prediction_id, explain_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    utc_now().isoformat(),
                    market,
                    row.get("symbol"),
                    row.get("data_source"),
                    row.get("data_quality"),
                    row.get("regime"),
                    row.get("model_score"),
                    row.get("signal"),
                    row.get("risk_result"),
                    json.dumps(row.get("trade_plan") or {}),
                    row.get("execution_result"),
                    row.get("prediction_id"),
                    json.dumps(row.get("explain") or {}),
                    json.dumps(row.get("payload") or {}),
                ),
            )

    def recent_cycles(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM autonomy_cycles ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def cycle_events(self, cycle_id: str, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM autonomy_symbol_events WHERE cycle_id=? ORDER BY id ASC LIMIT ?",
                (cycle_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("trade_plan_json", "explain_json", "payload_json"):
                try:
                    d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")
                except json.JSONDecodeError:
                    d[k.replace("_json", "")] = {}
            out.append(d)
        return out

    def update_cycle_summary(self, cycle_id: str, summary: dict, note: str = "", kill_switch: bool | None = None) -> None:
        with self._conn() as c:
            row = c.execute("SELECT summary_json, kill_switch FROM autonomy_cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            if not row:
                return
            payload = summary
            try:
                prev = json.loads(row["summary_json"] or "{}")
                if isinstance(prev, dict):
                    prev.update(summary)
                    payload = prev
            except json.JSONDecodeError:
                pass
            ks = row["kill_switch"] if kill_switch is None else (1 if kill_switch else 0)
            c.execute(
                "UPDATE autonomy_cycles SET summary_json=?, note=?, kill_switch=? WHERE cycle_id=?",
                (json.dumps(payload), note, ks, cycle_id),
            )

    def claim_order_key(self, key: str, symbol: str, signal: str, order_id: str | None = None) -> bool:
        """Return True if key was free and is now claimed (idempotency)."""
        now = utc_now().isoformat()
        with self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO autonomy_order_keys(dedupe_key, symbol, signal, created_at, order_id) VALUES (?,?,?,?,?)",
                    (key, symbol, signal, now, order_id),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def purge_old_order_keys(self, max_age_sec: float = 3600) -> None:
        # ISO compare is ok for UTC Z-less timestamps from utc_now
        with self._conn() as c:
            rows = c.execute("SELECT dedupe_key, created_at FROM autonomy_order_keys").fetchall()
        cut = utc_now().timestamp() - max_age_sec
        drop = []
        for r in rows:
            try:
                from datetime import datetime

                ts = datetime.fromisoformat(r["created_at"])
                if ts.timestamp() < cut:
                    drop.append(r["dedupe_key"])
            except Exception:  # noqa: BLE001
                continue
        if not drop:
            return
        with self._conn() as c:
            c.executemany("DELETE FROM autonomy_order_keys WHERE dedupe_key=?", [(k,) for k in drop])
