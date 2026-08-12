"""Order idempotency — same key must never create two submits."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class IdempotencyClaim:
    key: str
    claimed: bool
    duplicate: bool
    prior_status: str | None = None


class IdempotencyStore:
    """SQLite-backed claim store (append-only claims)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or Path(__file__).resolve().parents[1] / "logs" / "idempotency.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path))
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
              key TEXT PRIMARY KEY,
              symbol TEXT,
              side TEXT,
              created_at TEXT,
              status TEXT,
              order_id TEXT
            )
            """
        )
        return c

    def _init(self) -> None:
        with self._conn() as c:
            pass

    @staticmethod
    def make_key(
        *,
        symbol: str,
        side: str,
        signal: str,
        cycle_id: str,
        window_bucket: int,
        market: str = "BIST",
    ) -> str:
        raw = f"{market}|{symbol.upper()}|{side.upper()}|{signal}|{cycle_id}|{window_bucket}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        return f"TS-{symbol.upper()}-{digest}"

    def claim(self, key: str, *, symbol: str, side: str) -> IdempotencyClaim:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO idempotency_keys(key, symbol, side, created_at, status) VALUES (?,?,?,?,?)",
                    (key, symbol, side, now, "CLAIMED"),
                )
                return IdempotencyClaim(key=key, claimed=True, duplicate=False)
            except sqlite3.IntegrityError:
                row = c.execute(
                    "SELECT status FROM idempotency_keys WHERE key=?", (key,)
                ).fetchone()
                return IdempotencyClaim(
                    key=key,
                    claimed=False,
                    duplicate=True,
                    prior_status=row[0] if row else "UNKNOWN",
                )

    def mark_status(self, key: str, status: str, order_id: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE idempotency_keys SET status=?, order_id=COALESCE(?, order_id) WHERE key=?",
                (status, order_id, key),
            )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT key, symbol, side, created_at, status, order_id FROM idempotency_keys WHERE key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return {
            "key": row[0],
            "symbol": row[1],
            "side": row[2],
            "created_at": row[3],
            "status": row[4],
            "order_id": row[5],
        }
