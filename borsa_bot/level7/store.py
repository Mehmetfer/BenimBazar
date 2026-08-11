"""SQLite store for Level 7 research / hypothesis / experiment / memory artifacts."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT


class Level7Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "level7.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
                    CREATE TABLE IF NOT EXISTS research_questions (
                      id TEXT PRIMARY KEY,
                      question TEXT NOT NULL,
                      reason TEXT,
                      priority TEXT,
                      dataset TEXT,
                      status TEXT,
                      result TEXT,
                      created_at TEXT,
                      updated_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS hypotheses (
                      id TEXT PRIMARY KEY,
                      title TEXT NOT NULL,
                      statement TEXT NOT NULL,
                      status TEXT NOT NULL,
                      regime TEXT,
                      timeframe TEXT,
                      params_json TEXT,
                      metrics_json TEXT,
                      created_at TEXT,
                      updated_at TEXT,
                      note TEXT
                    );
                    CREATE TABLE IF NOT EXISTS experiments (
                      id TEXT PRIMARY KEY,
                      hypothesis_id TEXT,
                      stage TEXT NOT NULL,
                      status TEXT NOT NULL,
                      dataset TEXT,
                      metrics_json TEXT,
                      theoretical INTEGER DEFAULT 1,
                      created_at TEXT,
                      updated_at TEXT,
                      note TEXT
                    );
                    CREATE TABLE IF NOT EXISTS strategies (
                      id TEXT PRIMARY KEY,
                      name TEXT NOT NULL,
                      version TEXT NOT NULL,
                      status TEXT NOT NULL,
                      role TEXT,
                      regime TEXT,
                      timeframe TEXT,
                      params_json TEXT,
                      performance_json TEXT,
                      created_at TEXT,
                      updated_at TEXT,
                      note TEXT
                    );
                    CREATE TABLE IF NOT EXISTS pattern_memory (
                      id TEXT PRIMARY KEY,
                      feature_vector_json TEXT,
                      market_regime TEXT,
                      timeframe TEXT,
                      symbol TEXT,
                      outcome TEXT,
                      sample_size INTEGER,
                      created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS audit_log (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      ts TEXT,
                      agent TEXT,
                      action TEXT,
                      reason TEXT,
                      input_json TEXT,
                      output_json TEXT,
                      version TEXT,
                      result TEXT
                    );
                    CREATE TABLE IF NOT EXISTS journal (
                      id TEXT PRIMARY KEY,
                      symbol TEXT,
                      setup TEXT,
                      reason TEXT,
                      entry REAL,
                      stop REAL,
                      target REAL,
                      thesis TEXT,
                      decision TEXT,
                      outcome TEXT,
                      lesson TEXT,
                      created_at TEXT
                    );
                    """
                )
                c.commit()
            finally:
                c.close()

    def audit(
        self,
        *,
        agent: str,
        action: str,
        reason: str = "",
        input_data: dict | None = None,
        output_data: dict | None = None,
        version: str = "level7_v1",
        result: str = "OK",
    ) -> None:
        with self._lock:
            c = self._conn()
            try:
                c.execute(
                    "INSERT INTO audit_log(ts,agent,action,reason,input_json,output_json,version,result) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        utc_now().isoformat(),
                        agent,
                        action,
                        reason,
                        json.dumps(input_data or {}),
                        json.dumps(output_data or {}),
                        version,
                        result,
                    ),
                )
                c.commit()
            finally:
                c.close()

    def upsert_row(self, table: str, row: dict[str, Any], pk: str = "id") -> None:
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk)
        sql = (
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
        )
        with self._lock:
            c = self._conn()
            try:
                c.execute(sql, [row[k] for k in cols])
                c.commit()
            finally:
                c.close()

    def list_rows(self, table: str, *, where: str = "1=1", params: tuple = (), limit: int = 50) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY rowid DESC LIMIT ?", (*params, limit))
                return [dict(r) for r in cur.fetchall()]
            finally:
                c.close()

    def count(self, table: str, *, where: str = "1=1", params: tuple = ()) -> int:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params)
                return int(cur.fetchone()["n"])
            finally:
                c.close()
