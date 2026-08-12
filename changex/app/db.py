from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "changex.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              change_score REAL NOT NULL DEFAULT 50.0,
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at REAL NOT NULL,
              expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_listings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              owner_id INTEGER NOT NULL REFERENCES users(id),
              title TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL,
              subcategory TEXT NOT NULL DEFAULT '',
              condition TEXT NOT NULL DEFAULT 'good',
              location TEXT NOT NULL DEFAULT '',
              value_mandal INTEGER NOT NULL,
              accept_categories TEXT NOT NULL DEFAULT '[]',
              wanted_items TEXT NOT NULL DEFAULT '',
              min_value_mandal INTEGER NOT NULL DEFAULT 0,
              max_value_mandal INTEGER NOT NULL DEFAULT 0,
              photo_urls TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'active',
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listing_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              value_mandal INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trades (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id),
              initiator_id INTEGER NOT NULL REFERENCES users(id),
              counterparty_id INTEGER NOT NULL REFERENCES users(id),
              state TEXT NOT NULL,
              a_value_mandal INTEGER NOT NULL,
              b_value_mandal INTEGER NOT NULL,
              gap_mandal INTEGER NOT NULL,
              idempotency_key TEXT UNIQUE,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
              actor_id INTEGER,
              from_state TEXT,
              to_state TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              actor_id INTEGER,
              action TEXT NOT NULL,
              detail TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL
            );
            """
        )


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(check, digest)


def audit(conn: sqlite3.Connection, actor_id: int | None, action: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor_id, action, detail, created_at) VALUES (?,?,?,?)",
        (actor_id, action, detail, time.time()),
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
