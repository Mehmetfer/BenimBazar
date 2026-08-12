"""CHANGE X SQLite persistence + schema migrations."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "changex.db"

# Controllable failure injection for rollback tests (test-only).
_FAILURE_HOOK: Callable[[str], None] | None = None

# Soft metrics for SQLite contention (process-local).
LOCK_STATS: dict[str, int] = {
    "begin_immediate": 0,
    "busy_retries": 0,
    "busy_failures": 0,
    "rollbacks": 0,
    "commits": 0,
}


def set_failure_hook(hook: Callable[[str], None] | None) -> None:
    global _FAILURE_HOOK
    _FAILURE_HOOK = hook


def maybe_fail(stage: str) -> None:
    if _FAILURE_HOOK is not None:
        _FAILURE_HOOK(stage)


def reset_lock_stats() -> None:
    for k in LOCK_STATS:
        LOCK_STATS[k] = 0


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # timeout=30s cooperates with PRAGMA busy_timeout for lock waits
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def immediate_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE with busy retry — serializes writers under concurrency."""
    attempts = 0
    while True:
        attempts += 1
        try:
            LOCK_STATS["begin_immediate"] += 1
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "locked" in msg or "busy" in msg:
                LOCK_STATS["busy_retries"] += 1
                if attempts >= 8:
                    LOCK_STATS["busy_failures"] += 1
                    raise
                time.sleep(0.005 * attempts)
                continue
            raise
    try:
        yield conn
        maybe_fail("before_commit")
        conn.execute("COMMIT")
        LOCK_STATS["commits"] += 1
    except Exception:
        LOCK_STATS["rollbacks"] += 1
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              id TEXT PRIMARY KEY,
              applied_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              change_score REAL NOT NULL DEFAULT 50.0,
              user_risk_score REAL NOT NULL DEFAULT 0.0,
              suspended INTEGER NOT NULL DEFAULT 0,
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
              mandal_units INTEGER NOT NULL,
              accept_categories TEXT NOT NULL DEFAULT '[]',
              wanted_items TEXT NOT NULL DEFAULT '',
              min_mandal_units INTEGER NOT NULL DEFAULT 0,
              max_mandal_units INTEGER NOT NULL DEFAULT 0,
              photo_urls TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'PENDING_MODERATION',
              version INTEGER NOT NULL DEFAULT 1,
              moderation_version INTEGER NOT NULL DEFAULT 1,
              ai_result TEXT,
              ai_confidence REAL,
              ai_categories TEXT NOT NULL DEFAULT '[]',
              ai_policy_version TEXT,
              risk_level TEXT,
              moderation_priority INTEGER NOT NULL DEFAULT 0,
              moderation_reason TEXT NOT NULL DEFAULT '',
              moderation_updated_at REAL,
              approved_at REAL,
              approved_by INTEGER,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listing_photos (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
              url TEXT NOT NULL,
              moderation_status TEXT NOT NULL DEFAULT 'PENDING',
              moderation_version INTEGER NOT NULL DEFAULT 1,
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moderation_reviews (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
              moderation_version INTEGER NOT NULL,
              ai_result TEXT,
              ai_confidence REAL,
              ai_payload TEXT NOT NULL DEFAULT '{}',
              risk_level TEXT,
              priority INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              policy_version TEXT,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moderation_decisions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
              moderation_version INTEGER NOT NULL,
              moderator_id INTEGER,
              moderator_role TEXT,
              previous_status TEXT,
              new_status TEXT,
              decision TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              ai_result TEXT,
              ai_confidence REAL,
              correlation_id TEXT,
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listing_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              mandal_units INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trades (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              proposer_id INTEGER NOT NULL REFERENCES users(id),
              receiver_id INTEGER NOT NULL REFERENCES users(id),
              offered_listing_ids TEXT NOT NULL,
              requested_listing_ids TEXT NOT NULL,
              calculated_offered_mandal_units INTEGER NOT NULL,
              calculated_requested_mandal_units INTEGER NOT NULL,
              value_gap_mandal_units INTEGER NOT NULL,
              status TEXT NOT NULL,
              version INTEGER NOT NULL DEFAULT 1,
              idempotency_key TEXT UNIQUE,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              expires_at REAL,
              accepted_at REAL,
              cancelled_at REAL,
              completed_at REAL
            );

            CREATE TABLE IF NOT EXISTS trade_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
              actor_id INTEGER,
              from_state TEXT,
              to_state TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              correlation_id TEXT,
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS idempotency_keys (
              key TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              action TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id INTEGER NOT NULL,
              response_json TEXT NOT NULL,
              created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              actor_id INTEGER,
              action TEXT NOT NULL,
              entity TEXT,
              entity_id INTEGER,
              detail TEXT NOT NULL DEFAULT '',
              correlation_id TEXT,
              created_at REAL NOT NULL
            );
            """
        )
        _migrate(conn)


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent migrations from v0 schema (value_mandal / initiator_id)."""
    cols = _table_cols(conn, "trade_listings")
    if cols and "value_mandal" in cols and "mandal_units" not in cols:
        conn.execute("ALTER TABLE trade_listings ADD COLUMN mandal_units INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE trade_listings SET mandal_units = value_mandal")
    if cols and "version" not in cols:
        conn.execute("ALTER TABLE trade_listings ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if cols and "updated_at" not in cols:
        conn.execute("ALTER TABLE trade_listings ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
        conn.execute("UPDATE trade_listings SET updated_at = created_at WHERE updated_at = 0")
    if cols and "min_mandal_units" not in cols and "min_value_mandal" in cols:
        conn.execute(
            "ALTER TABLE trade_listings ADD COLUMN min_mandal_units INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute("UPDATE trade_listings SET min_mandal_units = min_value_mandal")
    if cols and "max_mandal_units" not in cols and "max_value_mandal" in cols:
        conn.execute(
            "ALTER TABLE trade_listings ADD COLUMN max_mandal_units INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute("UPDATE trade_listings SET max_mandal_units = max_value_mandal")
    # Trust & Safety V1 columns
    if cols:
        for col, decl in [
            ("moderation_version", "INTEGER NOT NULL DEFAULT 1"),
            ("ai_result", "TEXT"),
            ("ai_confidence", "REAL"),
            ("ai_categories", "TEXT NOT NULL DEFAULT '[]'"),
            ("ai_policy_version", "TEXT"),
            ("risk_level", "TEXT"),
            ("moderation_priority", "INTEGER NOT NULL DEFAULT 0"),
            ("moderation_reason", "TEXT NOT NULL DEFAULT ''"),
            ("moderation_updated_at", "REAL"),
            ("approved_at", "REAL"),
            ("approved_by", "INTEGER"),
        ]:
            if col not in cols:
                try:
                    conn.execute(f"ALTER TABLE trade_listings ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass
        # Pre-moderation era ACTIVE listings were already public → APPROVED
        conn.execute(
            "UPDATE trade_listings SET status = 'APPROVED', approved_at = COALESCE(approved_at, created_at) "
            "WHERE upper(status) = 'ACTIVE'"
        )
        conn.execute(
            "UPDATE trade_listings SET status = upper(status) WHERE status GLOB '[a-z]*'"
        )

    user_cols = _table_cols(conn, "users")
    if user_cols:
        if "user_risk_score" not in user_cols:
            try:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN user_risk_score REAL NOT NULL DEFAULT 0.0"
                )
            except sqlite3.OperationalError:
                pass
        if "suspended" not in user_cols:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS listing_photos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
          url TEXT NOT NULL,
          moderation_status TEXT NOT NULL DEFAULT 'PENDING',
          moderation_version INTEGER NOT NULL DEFAULT 1,
          created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS moderation_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
          moderation_version INTEGER NOT NULL,
          ai_result TEXT,
          ai_confidence REAL,
          ai_payload TEXT NOT NULL DEFAULT '{}',
          risk_level TEXT,
          priority INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          policy_version TEXT,
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS moderation_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          listing_id INTEGER NOT NULL REFERENCES trade_listings(id) ON DELETE CASCADE,
          moderation_version INTEGER NOT NULL,
          moderator_id INTEGER,
          moderator_role TEXT,
          previous_status TEXT,
          new_status TEXT,
          decision TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          ai_result TEXT,
          ai_confidence REAL,
          correlation_id TEXT,
          created_at REAL NOT NULL
        );
        """
    )

    item_cols = _table_cols(conn, "listing_items")
    if item_cols and "value_mandal" in item_cols and "mandal_units" not in item_cols:
        conn.execute("ALTER TABLE listing_items ADD COLUMN mandal_units INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE listing_items SET mandal_units = value_mandal")

    trade_cols = _table_cols(conn, "trades")
    if trade_cols and "initiator_id" in trade_cols and "proposer_id" not in trade_cols:
        # Legacy table — leave old rows; new code uses new columns when present.
        for col, decl in [
            ("proposer_id", "INTEGER"),
            ("receiver_id", "INTEGER"),
            ("offered_listing_ids", "TEXT"),
            ("requested_listing_ids", "TEXT"),
            ("calculated_offered_mandal_units", "INTEGER NOT NULL DEFAULT 0"),
            ("calculated_requested_mandal_units", "INTEGER NOT NULL DEFAULT 0"),
            ("value_gap_mandal_units", "INTEGER NOT NULL DEFAULT 0"),
            ("status", "TEXT"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("expires_at", "REAL"),
            ("accepted_at", "REAL"),
            ("cancelled_at", "REAL"),
            ("completed_at", "REAL"),
        ]:
            if col not in trade_cols:
                try:
                    conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass
        # Best-effort backfill
        try:
            conn.execute(
                """
                UPDATE trades SET
                  proposer_id = COALESCE(proposer_id, initiator_id),
                  receiver_id = COALESCE(receiver_id, counterparty_id),
                  status = COALESCE(status, state),
                  calculated_offered_mandal_units = COALESCE(calculated_offered_mandal_units, b_value_mandal, 0),
                  calculated_requested_mandal_units = COALESCE(calculated_requested_mandal_units, a_value_mandal, 0),
                  value_gap_mandal_units = COALESCE(value_gap_mandal_units, gap_mandal, 0),
                  requested_listing_ids = COALESCE(requested_listing_ids, json_array(listing_id)),
                  offered_listing_ids = COALESCE(offered_listing_ids, '[]')
                """
            )
        except sqlite3.OperationalError:
            pass

    audit_cols = _table_cols(conn, "audit_logs")
    if audit_cols:
        if "entity" not in audit_cols:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN entity TEXT")
        if "entity_id" not in audit_cols:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN entity_id INTEGER")
        if "correlation_id" not in audit_cols:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN correlation_id TEXT")


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


def audit(
    conn: sqlite3.Connection,
    *,
    actor_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    detail: str = "",
    correlation_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs(actor_id, action, entity, entity_id, detail, correlation_id, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            actor_id,
            action,
            entity,
            entity_id,
            detail,
            correlation_id or str(uuid.uuid4()),
            time.time(),
        ),
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default
    return json.loads(raw)
