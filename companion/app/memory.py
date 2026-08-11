from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import DATA_DIR, DB_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class MemoryItem:
    id: int
    key: str
    value: str
    importance: int
    updated_at: str


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str


class MemoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 50,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert(self, key: str, value: str, importance: int = 70) -> MemoryItem:
        key = key.strip().lower()
        value = value.strip()
        importance = max(1, min(100, importance))
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories(key, value, importance, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    importance=MAX(memories.importance, excluded.importance),
                    updated_at=excluded.updated_at
                """,
                (key, value, importance, now),
            )
            row = conn.execute(
                "SELECT id, key, value, importance, updated_at FROM memories WHERE key = ?",
                (key,),
            ).fetchone()
        return MemoryItem(**dict(row))

    def get(self, key: str) -> MemoryItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, key, value, importance, updated_at FROM memories WHERE key = ?",
                (key.strip().lower(),),
            ).fetchone()
        return MemoryItem(**dict(row)) if row else None

    def list_all(self, limit: int = 50) -> list[MemoryItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, key, value, importance, updated_at
                FROM memories
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [MemoryItem(**dict(r)) for r in rows]

    def add_message(self, role: str, content: str) -> ChatMessage:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(role, content, created_at) VALUES(?, ?, ?)",
                (role, content, now),
            )
        return ChatMessage(role=role, content=content, created_at=now)

    def recent_messages(self, limit: int = 20) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at FROM messages
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        items = [ChatMessage(**dict(r)) for r in rows]
        items.reverse()
        return items

    def clear_messages(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages")


NAME_PATTERNS: list[tuple[re.Pattern[str], str, int]] = [
    (
        re.compile(
            r"(?:benim\s+)?(?:adım|ismim)\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\b(?!\s*\?)",
            re.I,
        ),
        "user_name",
        95,
    ),
    (
        re.compile(
            r"(?:beni)\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\s+(?:diye çağır|diye hitap et)",
            re.I,
        ),
        "preferred_name",
        90,
    ),
    (
        re.compile(r"kedimin\s+adı\s+([A-Za-zÇĞİÖŞÜçğıöşü]{2,30})\b", re.I),
        "cat_name",
        85,
    ),
    (
        re.compile(
            r"(?:(?P<city1>[A-Za-zÇĞİÖŞÜçğıöşü]{2,40})\s*(?:şehrinde|şehrindeyim)|(?:şehir|yaşıyorum)\s*:?\s*(?P<city2>[A-Za-zÇĞİÖŞÜçğıöşü]{2,40}))",
            re.I,
        ),
        "city",
        70,
    ),
]

_QUESTION_TOKENS = {
    "neydi",
    "nedir",
    "ne",
    "kim",
    "hangi",
    "kaç",
    "nasıl",
    "nerede",
    "hatırlıyor",
    "biliyor",
}


def extract_memories(text: str) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    raw = text or ""
    for pattern, key, importance in NAME_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        if key == "city":
            value = (match.groupdict().get("city1") or match.groupdict().get("city2") or "").strip()
        else:
            value = match.group(1).strip()
        if not value or value.casefold() in _QUESTION_TOKENS:
            continue
        if "?" in raw and key in {"user_name", "cat_name", "preferred_name"}:
            # Avoid treating recall questions as teaching statements.
            continue
        found.append((key, value, importance))
    return found

def memory_context(items: Iterable[MemoryItem]) -> str:
    lines = [f"- {m.key}: {m.value}" for m in items]
    if not lines:
        return ""
    return "Kullanıcı hakkında bilinenler:\n" + "\n".join(lines)
