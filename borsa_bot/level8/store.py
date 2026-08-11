"""Level 8 store — snapshots, knowledge, drift, reports, feedback, budgets."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT
from level7.store import Level7Store


class Level8Store:
    """Extends Level7Store path with L8 tables; shares same DB file by default."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "level8.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Also ensure L7 tables exist on this DB so engines can share one file
        self.l7 = Level7Store(path=self.path)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._lock:
            c = self._conn()
            try:
                c.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS decision_snapshots (
                      decision_id TEXT PRIMARY KEY,
                      symbol TEXT,
                      market_type TEXT,
                      timestamp TEXT NOT NULL,
                      market_regime TEXT,
                      timeframe TEXT,
                      features_json TEXT,
                      indicators_json TEXT,
                      model TEXT,
                      prompt_version TEXT,
                      strategy_version TEXT,
                      confidence REAL,
                      uncertainty TEXT,
                      signal TEXT,
                      entry REAL,
                      stop REAL,
                      target REAL,
                      expected_value REAL,
                      data_kind TEXT,
                      provider TEXT,
                      data_timestamp TEXT,
                      market_snapshot_json TEXT,
                      outcome_json TEXT,
                      error_class TEXT,
                      root_cause TEXT,
                      created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS knowledge_memory (
                      id TEXT PRIMARY KEY,
                      observation TEXT,
                      hypothesis_id TEXT,
                      experiment_id TEXT,
                      result TEXT,
                      confidence REAL,
                      evidence_json TEXT,
                      freshness TEXT,
                      last_validated TEXT,
                      status TEXT,
                      created_at TEXT,
                      updated_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS drift_events (
                      id TEXT PRIMARY KEY,
                      drift_type TEXT,
                      severity TEXT,
                      detail_json TEXT,
                      created_at TEXT,
                      status TEXT
                    );
                    CREATE TABLE IF NOT EXISTS learning_reports (
                      id TEXT PRIMARY KEY,
                      period TEXT,
                      content_json TEXT,
                      created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS human_feedback (
                      id TEXT PRIMARY KEY,
                      decision_id TEXT,
                      label TEXT,
                      note TEXT,
                      created_at TEXT,
                      aggregated INTEGER DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS research_budget (
                      day_key TEXT PRIMARY KEY,
                      experiments INTEGER DEFAULT 0,
                      api_calls INTEGER DEFAULT 0,
                      model_calls INTEGER DEFAULT 0,
                      max_experiments INTEGER DEFAULT 20,
                      max_api_calls INTEGER DEFAULT 400,
                      max_model_calls INTEGER DEFAULT 100
                    );
                    CREATE TABLE IF NOT EXISTS baselines (
                      id TEXT PRIMARY KEY,
                      version TEXT,
                      metrics_json TEXT,
                      created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS learning_audit (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      ts TEXT,
                      agent TEXT,
                      action TEXT,
                      reason TEXT,
                      payload_json TEXT,
                      result TEXT
                    );
                    """
                )
                c.commit()
            finally:
                c.close()

    def audit(self, *, agent: str, action: str, reason: str = "", payload: dict | None = None, result: str = "OK") -> None:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO learning_audit(ts,agent,action,reason,payload_json,result) VALUES(?,?,?,?,?,?)",
                    (utc_now().isoformat(), agent, action, reason, json.dumps(payload or {}), result),
                )
                c.commit()
            finally:
                c.close()

    def upsert(self, table: str, row: dict[str, Any], pk: str = "id") -> None:
        cols = list(row.keys())
        ph = ",".join("?" for _ in cols)
        upd = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk)
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph}) ON CONFLICT({pk}) DO UPDATE SET {upd}"
        with self._lock:
            c = self._conn()
            try:
                c.execute(sql, [row[k] for k in cols])
                c.commit()
            finally:
                c.close()

    def list_rows(self, table: str, *, where: str = "1=1", params: tuple = (), limit: int = 50, order: str = "rowid DESC") -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ?", (*params, limit))
                return [dict(r) for r in cur.fetchall()]
            finally:
                c.close()

    def get(self, table: str, pk: str, value: str) -> dict | None:
        rows = self.list_rows(table, where=f"{pk}=?", params=(value,), limit=1)
        return rows[0] if rows else None

    def count(self, table: str, *, where: str = "1=1", params: tuple = ()) -> int:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params)
                return int(cur.fetchone()["n"])
            finally:
                c.close()
