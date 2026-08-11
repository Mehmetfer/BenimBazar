from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from config.models import utc_now
from config.settings import ROOT
from favorites.models import DEFAULT_GROUPS, FavoriteRecord, PriceAlertRule


class FavoritesStore:
    """SQLite favorites. Independent from portfolio ledger."""

    def __init__(self, path: Path | None = None, user_id: str = "default") -> None:
        self.path = path or (ROOT / "database" / "favorites.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    favorite_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    priority INTEGER DEFAULT 50,
                    notes TEXT DEFAULT '',
                    strategy_preference TEXT DEFAULT '["SWING"]',
                    notification_preferences TEXT DEFAULT '{}',
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_ai_signal TEXT,
                    last_ai_confidence REAL,
                    UNIQUE(user_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS favorite_groups (
                    group_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, name)
                );
                CREATE TABLE IF NOT EXISTS favorite_group_members (
                    group_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY(group_id, symbol, user_id)
                );
                CREATE TABLE IF NOT EXISTS favorite_price_alerts (
                    alert_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    threshold REAL,
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favorite_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favorite_signal_stats (
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL,
                    outcome_pct REAL,
                    closed INTEGER DEFAULT 0,
                    ts TEXT NOT NULL
                );
                """
            )
            for name in DEFAULT_GROUPS:
                c.execute(
                    """
                    INSERT OR IGNORE INTO favorite_groups(group_id, user_id, name, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.user_id, name, utc_now().isoformat()),
                )

    def list_favorites(self, active_only: bool = True) -> list[FavoriteRecord]:
        q = "SELECT * FROM favorites WHERE user_id=?"
        if active_only:
            q += " AND active=1"
        q += " ORDER BY priority DESC, symbol ASC"
        with self._conn() as c:
            rows = c.execute(q, (self.user_id,)).fetchall()
        out = []
        for r in rows:
            out.append(self._row_to_fav(r))
        return out

    def symbols(self) -> set[str]:
        return {f.symbol for f in self.list_favorites()}

    def get(self, symbol: str) -> FavoriteRecord | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM favorites WHERE user_id=? AND symbol=?",
                (self.user_id, symbol.upper()),
            ).fetchone()
        return self._row_to_fav(row) if row else None

    def is_favorite(self, symbol: str) -> bool:
        f = self.get(symbol.upper())
        return bool(f and f.active)

    def toggle(self, symbol: str) -> FavoriteRecord:
        symbol = symbol.upper()
        existing = self.get(symbol)
        if existing and existing.active:
            self.remove(symbol)
            existing.active = False
            return existing
        if existing and not existing.active:
            return self.add(symbol, reactivate=True)
        return self.add(symbol)

    def add(self, symbol: str, *, reactivate: bool = False, notes: str = "", priority: int = 50) -> FavoriteRecord:
        symbol = symbol.upper()
        now = utc_now().isoformat()
        with self._conn() as c:
            if reactivate:
                c.execute(
                    "UPDATE favorites SET active=1, updated_at=?, notes=COALESCE(NULLIF(?, ''), notes) WHERE user_id=? AND symbol=?",
                    (now, notes, self.user_id, symbol),
                )
            else:
                fid = uuid.uuid4().hex
                c.execute(
                    """
                    INSERT INTO favorites(favorite_id, user_id, symbol, priority, notes,
                        strategy_preference, notification_preferences, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, symbol) DO UPDATE SET
                        active=1, updated_at=excluded.updated_at,
                        notes=CASE WHEN excluded.notes!='' THEN excluded.notes ELSE favorites.notes END
                    """,
                    (
                        fid,
                        self.user_id,
                        symbol,
                        priority,
                        notes,
                        json.dumps(["SWING"]),
                        json.dumps({"voice": True, "push": True}),
                        now,
                        now,
                    ),
                )
        self.add_event(symbol, "FAVORITE_ADDED", f"{symbol} favorilere eklendi")
        fav = self.get(symbol)
        assert fav is not None
        return fav

    def remove(self, symbol: str) -> None:
        symbol = symbol.upper()
        with self._conn() as c:
            c.execute(
                "UPDATE favorites SET active=0, updated_at=? WHERE user_id=? AND symbol=?",
                (utc_now().isoformat(), self.user_id, symbol),
            )
        self.add_event(symbol, "FAVORITE_REMOVED", f"{symbol} favorilerden çıkarıldı")

    def update(
        self,
        symbol: str,
        *,
        notes: str | None = None,
        priority: int | None = None,
        strategy_preference: list[str] | None = None,
        notification_preferences: dict | None = None,
    ) -> FavoriteRecord:
        symbol = symbol.upper()
        fav = self.get(symbol)
        if not fav or not fav.active:
            raise ValueError("not_favorite")
        notes_v = fav.notes if notes is None else notes
        pri = fav.priority if priority is None else int(priority)
        strat = fav.strategy_preference if strategy_preference is None else strategy_preference
        npref = fav.notification_preferences if notification_preferences is None else notification_preferences
        with self._conn() as c:
            c.execute(
                """
                UPDATE favorites SET notes=?, priority=?, strategy_preference=?,
                    notification_preferences=?, updated_at=?
                WHERE user_id=? AND symbol=?
                """,
                (
                    notes_v,
                    max(0, min(100, pri)),
                    json.dumps(strat),
                    json.dumps(npref),
                    utc_now().isoformat(),
                    self.user_id,
                    symbol,
                ),
            )
        out = self.get(symbol)
        assert out is not None
        return out

    def set_groups(self, symbol: str, group_names: list[str]) -> list[str]:
        symbol = symbol.upper()
        with self._conn() as c:
            c.execute(
                "DELETE FROM favorite_group_members WHERE user_id=? AND symbol=?",
                (self.user_id, symbol),
            )
            for name in group_names:
                row = c.execute(
                    "SELECT group_id FROM favorite_groups WHERE user_id=? AND name=?",
                    (self.user_id, name),
                ).fetchone()
                if not row:
                    gid = uuid.uuid4().hex
                    c.execute(
                        "INSERT INTO favorite_groups(group_id, user_id, name, created_at) VALUES (?,?,?,?)",
                        (gid, self.user_id, name, utc_now().isoformat()),
                    )
                else:
                    gid = row["group_id"]
                c.execute(
                    "INSERT OR IGNORE INTO favorite_group_members(group_id, symbol, user_id) VALUES (?,?,?)",
                    (gid, symbol, self.user_id),
                )
        return group_names

    def list_groups(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT g.group_id, g.name, COUNT(m.symbol) AS n FROM favorite_groups g "
                "LEFT JOIN favorite_group_members m ON m.group_id=g.group_id AND m.user_id=g.user_id "
                "WHERE g.user_id=? GROUP BY g.group_id ORDER BY g.name",
                (self.user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def add_price_alert(self, symbol: str, kind: str, threshold: float | None) -> PriceAlertRule:
        aid = uuid.uuid4().hex
        rule = PriceAlertRule(alert_id=aid, symbol=symbol.upper(), kind=kind.upper(), threshold=threshold)
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO favorite_price_alerts(alert_id, user_id, symbol, kind, threshold, active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (aid, self.user_id, rule.symbol, rule.kind, threshold, rule.created_at),
            )
        return rule

    def list_price_alerts(self, symbol: str | None = None) -> list[PriceAlertRule]:
        q = "SELECT * FROM favorite_price_alerts WHERE user_id=? AND active=1"
        args: list = [self.user_id]
        if symbol:
            q += " AND symbol=?"
            args.append(symbol.upper())
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [
            PriceAlertRule(
                alert_id=r["alert_id"],
                symbol=r["symbol"],
                kind=r["kind"],
                threshold=r["threshold"],
                active=bool(r["active"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def add_event(self, symbol: str, event_type: str, message: str, payload: dict | None = None) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO favorite_events(user_id, symbol, event_type, message, payload_json, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.user_id,
                    symbol.upper(),
                    event_type,
                    message,
                    json.dumps(payload or {}),
                    utc_now().isoformat(),
                ),
            )

    def timeline(self, symbol: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM favorite_events WHERE user_id=? AND symbol=? ORDER BY id DESC LIMIT ?",
                (self.user_id, symbol.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_last_signal(self, symbol: str, signal: str, confidence: float) -> str | None:
        """Returns previous signal if changed."""
        fav = self.get(symbol)
        prev = fav.last_ai_signal if fav else None
        with self._conn() as c:
            c.execute(
                "UPDATE favorites SET last_ai_signal=?, last_ai_confidence=?, updated_at=? WHERE user_id=? AND symbol=?",
                (signal, confidence, utc_now().isoformat(), self.user_id, symbol.upper()),
            )
        return prev

    def record_signal_outcome(self, symbol: str, signal: str, confidence: float, outcome_pct: float | None = None) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO favorite_signal_stats(user_id, symbol, signal, confidence, outcome_pct, closed, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.user_id,
                    symbol.upper(),
                    signal,
                    confidence,
                    outcome_pct,
                    1 if outcome_pct is not None else 0,
                    utc_now().isoformat(),
                ),
            )

    def performance(self) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT outcome_pct FROM favorite_signal_stats WHERE user_id=? AND closed=1 AND outcome_pct IS NOT NULL",
                (self.user_id,),
            ).fetchall()
        outcomes = [float(r["outcome_pct"]) for r in rows]
        if not outcomes:
            return {
                "signals": 0,
                "winners": 0,
                "losers": 0,
                "win_rate": None,
                "avg_win": None,
                "avg_loss": None,
                "expectancy": None,
                "note": "Henüz kapanmış favori sinyal sonucu yok (analiz amaçlı).",
            }
        wins = [x for x in outcomes if x > 0]
        losses = [x for x in outcomes if x <= 0]
        wr = len(wins) / len(outcomes) * 100
        avg_w = sum(wins) / len(wins) if wins else 0.0
        avg_l = sum(losses) / len(losses) if losses else 0.0
        exp = (len(wins) / len(outcomes)) * avg_w + (len(losses) / len(outcomes)) * avg_l
        return {
            "signals": len(outcomes),
            "winners": len(wins),
            "losers": len(losses),
            "win_rate": round(wr, 1),
            "avg_win": round(avg_w, 2),
            "avg_loss": round(avg_l, 2),
            "expectancy": round(exp, 3),
            "note": "Analiz amaçlı — kâr garantisi yok.",
        }

    def _row_to_fav(self, r: sqlite3.Row) -> FavoriteRecord:
        groups: list[str] = []
        with self._conn() as c:
            grows = c.execute(
                """
                SELECT g.name FROM favorite_group_members m
                JOIN favorite_groups g ON g.group_id=m.group_id
                WHERE m.user_id=? AND m.symbol=?
                """,
                (r["user_id"], r["symbol"]),
            ).fetchall()
            groups = [g["name"] for g in grows]
        try:
            strat = json.loads(r["strategy_preference"] or "[]")
        except json.JSONDecodeError:
            strat = ["SWING"]
        try:
            npref = json.loads(r["notification_preferences"] or "{}")
        except json.JSONDecodeError:
            npref = {}
        return FavoriteRecord(
            favorite_id=r["favorite_id"],
            user_id=r["user_id"],
            symbol=r["symbol"],
            priority=int(r["priority"] or 50),
            notes=r["notes"] or "",
            strategy_preference=list(strat),
            notification_preferences=dict(npref),
            active=bool(r["active"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            groups=groups,
            last_ai_signal=r["last_ai_signal"],
            last_ai_confidence=r["last_ai_confidence"],
        )
