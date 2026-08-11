from __future__ import annotations

import sqlite3
from pathlib import Path

from config.models import utc_now
from config.settings import ROOT


class NotificationLog:
    """Persists every channel delivery attempt. Never stores secrets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "notifications.db")
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
                CREATE TABLE IF NOT EXISTS notification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    symbol TEXT,
                    event_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message TEXT NOT NULL,
                    delivery_status TEXT NOT NULL,
                    provider TEXT,
                    error TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS in_app_inbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    symbol TEXT,
                    event_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    sound_profile TEXT,
                    tts_text TEXT,
                    payload_json TEXT,
                    read INTEGER DEFAULT 0
                )
                """
            )

    def write_delivery(
        self,
        *,
        event_id: str,
        symbol: str | None,
        event_type: str,
        priority: str,
        channel: str,
        message: str,
        delivery_status: str,
        provider: str | None = None,
        error: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        # Scrub accidental secrets from message/error
        safe_msg = _scrub(message)
        safe_err = _scrub(error) if error else None
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO notification_log
                (event_id, timestamp, symbol, event_type, priority, channel, message,
                 delivery_status, provider, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    timestamp or utc_now().isoformat(),
                    symbol,
                    event_type,
                    priority,
                    channel,
                    safe_msg,
                    delivery_status,
                    provider,
                    safe_err,
                ),
            )

    def write_in_app(
        self,
        *,
        event_id: str,
        symbol: str | None,
        event_type: str,
        priority: str,
        title: str,
        message: str,
        sound_profile: str | None,
        tts_text: str | None,
        payload_json: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO in_app_inbox
                (event_id, timestamp, symbol, event_type, priority, title, message,
                 sound_profile, tts_text, payload_json, read)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    event_id,
                    timestamp or utc_now().isoformat(),
                    symbol,
                    event_type,
                    priority,
                    title,
                    _scrub(message),
                    sound_profile,
                    tts_text,
                    payload_json,
                ),
            )

    def recent_log(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM notification_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def inbox(self, limit: int = 50, unread_only: bool = False) -> list[dict]:
        q = "SELECT * FROM in_app_inbox"
        if unread_only:
            q += " WHERE read=0"
        q += " ORDER BY id DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mark_read(self, event_id: str | None = None) -> int:
        with self._conn() as c:
            if event_id:
                cur = c.execute("UPDATE in_app_inbox SET read=1 WHERE event_id=?", (event_id,))
            else:
                cur = c.execute("UPDATE in_app_inbox SET read=1 WHERE read=0")
            return cur.rowcount


def _scrub(text: str | None) -> str:
    if not text:
        return ""
    banned = ("api_key", "apikey", "password", "token", "secret", "authorization")
    lower = text.lower()
    for b in banned:
        if b in lower:
            return "[REDACTED_SENSITIVE]"
    return text
