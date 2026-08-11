from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from config.models import utc_now
from config.settings import ROOT
from favorites.models import DEFAULT_GROUPS, FavoriteRecord, PriceAlertRule

VALID_MARKETS = frozenset({"BIST", "CRYPTO"})


def _norm_market(market_type: str | None) -> str:
    m = (market_type or "BIST").strip().upper()
    return m if m in VALID_MARKETS else "BIST"


class FavoritesStore:
    """SQLite favorites. Independent from portfolio ledger.

    Schema key: UNIQUE(user_id, market_type, symbol) so BIST and CRYPTO
    watchlists stay separate (same ticker string can exist in both planes).
    """

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
                    market_type TEXT NOT NULL DEFAULT 'BIST',
                    priority INTEGER DEFAULT 50,
                    notes TEXT DEFAULT '',
                    strategy_preference TEXT DEFAULT '["SWING"]',
                    notification_preferences TEXT DEFAULT '{}',
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_ai_signal TEXT,
                    last_ai_confidence REAL,
                    UNIQUE(user_id, market_type, symbol)
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
                    market_type TEXT NOT NULL DEFAULT 'BIST',
                    PRIMARY KEY(group_id, symbol, user_id, market_type)
                );
                CREATE TABLE IF NOT EXISTS favorite_price_alerts (
                    alert_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL DEFAULT 'BIST',
                    kind TEXT NOT NULL,
                    threshold REAL,
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favorite_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL DEFAULT 'BIST',
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    ts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favorite_signal_stats (
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL DEFAULT 'BIST',
                    signal TEXT NOT NULL,
                    confidence REAL,
                    outcome_pct REAL,
                    closed INTEGER DEFAULT 0,
                    ts TEXT NOT NULL
                );
                """
            )
            self._migrate_market_type(c)
            for name in DEFAULT_GROUPS:
                c.execute(
                    """
                    INSERT OR IGNORE INTO favorite_groups(group_id, user_id, name, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.user_id, name, utc_now().isoformat()),
                )

    def _migrate_market_type(self, c: sqlite3.Connection) -> None:
        """Additive migration for DBs created before market_type existed."""
        cols = {r[1] for r in c.execute("PRAGMA table_info(favorites)").fetchall()}
        if "market_type" not in cols:
            c.execute("ALTER TABLE favorites ADD COLUMN market_type TEXT NOT NULL DEFAULT 'BIST'")
            # Rebuild unique index: drop old UNIQUE(user_id,symbol) by table recreate if needed
            # SQLite keeps old unique if table was created with it — recreate when conflict constraint differs
            try:
                c.execute(
                    """
                    CREATE TABLE IF NOT EXISTS favorites_v2 (
                        favorite_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        market_type TEXT NOT NULL DEFAULT 'BIST',
                        priority INTEGER DEFAULT 50,
                        notes TEXT DEFAULT '',
                        strategy_preference TEXT DEFAULT '["SWING"]',
                        notification_preferences TEXT DEFAULT '{}',
                        active INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_ai_signal TEXT,
                        last_ai_confidence REAL,
                        UNIQUE(user_id, market_type, symbol)
                    )
                    """
                )
                c.execute(
                    """
                    INSERT OR IGNORE INTO favorites_v2(
                        favorite_id, user_id, symbol, market_type, priority, notes,
                        strategy_preference, notification_preferences, active,
                        created_at, updated_at, last_ai_signal, last_ai_confidence
                    )
                    SELECT favorite_id, user_id, symbol, COALESCE(market_type,'BIST'), priority, notes,
                        strategy_preference, notification_preferences, active,
                        created_at, updated_at, last_ai_signal, last_ai_confidence
                    FROM favorites
                    """
                )
                c.execute("DROP TABLE favorites")
                c.execute("ALTER TABLE favorites_v2 RENAME TO favorites")
            except sqlite3.Error:
                pass
        # Ensure child tables have market_type
        for table in ("favorite_group_members", "favorite_price_alerts", "favorite_events", "favorite_signal_stats"):
            try:
                tcols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
            except sqlite3.Error:
                continue
            if "market_type" not in tcols:
                try:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN market_type TEXT NOT NULL DEFAULT 'BIST'")
                except sqlite3.Error:
                    pass

    def list_favorites(self, active_only: bool = True, market_type: str | None = None) -> list[FavoriteRecord]:
        q = "SELECT * FROM favorites WHERE user_id=?"
        args: list = [self.user_id]
        if market_type is not None:
            q += " AND market_type=?"
            args.append(_norm_market(market_type))
        if active_only:
            q += " AND active=1"
        q += " ORDER BY priority DESC, symbol ASC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [self._row_to_fav(r) for r in rows]

    def symbols(self, market_type: str | None = "BIST") -> set[str]:
        """Default BIST so TradingService universe is unchanged."""
        return {f.symbol for f in self.list_favorites(market_type=market_type)}

    def get(self, symbol: str, market_type: str = "BIST") -> FavoriteRecord | None:
        mt = _norm_market(market_type)
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM favorites WHERE user_id=? AND market_type=? AND symbol=?",
                (self.user_id, mt, symbol.upper()),
            ).fetchone()
        return self._row_to_fav(row) if row else None

    def is_favorite(self, symbol: str, market_type: str = "BIST") -> bool:
        f = self.get(symbol.upper(), market_type=market_type)
        return bool(f and f.active)

    def toggle(self, symbol: str, market_type: str = "BIST") -> FavoriteRecord:
        symbol = symbol.upper()
        mt = _norm_market(market_type)
        existing = self.get(symbol, market_type=mt)
        if existing and existing.active:
            self.remove(symbol, market_type=mt)
            existing.active = False
            return existing
        if existing and not existing.active:
            return self.add(symbol, reactivate=True, market_type=mt)
        return self.add(symbol, market_type=mt)

    def add(
        self,
        symbol: str,
        *,
        reactivate: bool = False,
        notes: str = "",
        priority: int = 50,
        market_type: str = "BIST",
    ) -> FavoriteRecord:
        symbol = symbol.upper()
        mt = _norm_market(market_type)
        now = utc_now().isoformat()
        with self._conn() as c:
            if reactivate:
                c.execute(
                    "UPDATE favorites SET active=1, updated_at=?, notes=COALESCE(NULLIF(?, ''), notes) "
                    "WHERE user_id=? AND market_type=? AND symbol=?",
                    (now, notes, self.user_id, mt, symbol),
                )
            else:
                fid = uuid.uuid4().hex
                c.execute(
                    """
                    INSERT INTO favorites(favorite_id, user_id, symbol, market_type, priority, notes,
                        strategy_preference, notification_preferences, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, market_type, symbol) DO UPDATE SET
                        active=1, updated_at=excluded.updated_at,
                        notes=CASE WHEN excluded.notes!='' THEN excluded.notes ELSE favorites.notes END
                    """,
                    (
                        fid,
                        self.user_id,
                        symbol,
                        mt,
                        priority,
                        notes,
                        json.dumps(["SWING"]),
                        json.dumps({"voice": True, "push": True}),
                        now,
                        now,
                    ),
                )
        self.add_event(symbol, "FAVORITE_ADDED", f"{symbol} favorilere eklendi", market_type=mt)
        fav = self.get(symbol, market_type=mt)
        assert fav is not None
        return fav

    def remove(self, symbol: str, market_type: str = "BIST") -> None:
        symbol = symbol.upper()
        mt = _norm_market(market_type)
        with self._conn() as c:
            c.execute(
                "UPDATE favorites SET active=0, updated_at=? WHERE user_id=? AND market_type=? AND symbol=?",
                (utc_now().isoformat(), self.user_id, mt, symbol),
            )
        self.add_event(symbol, "FAVORITE_REMOVED", f"{symbol} favorilerden çıkarıldı", market_type=mt)

    def update(
        self,
        symbol: str,
        *,
        notes: str | None = None,
        priority: int | None = None,
        strategy_preference: list[str] | None = None,
        notification_preferences: dict | None = None,
        market_type: str = "BIST",
    ) -> FavoriteRecord:
        symbol = symbol.upper()
        mt = _norm_market(market_type)
        fav = self.get(symbol, market_type=mt)
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
                WHERE user_id=? AND market_type=? AND symbol=?
                """,
                (
                    notes_v,
                    max(0, min(100, pri)),
                    json.dumps(strat),
                    json.dumps(npref),
                    utc_now().isoformat(),
                    self.user_id,
                    mt,
                    symbol,
                ),
            )
        out = self.get(symbol, market_type=mt)
        assert out is not None
        return out

    def set_groups(self, symbol: str, group_names: list[str], market_type: str = "BIST") -> list[str]:
        symbol = symbol.upper()
        mt = _norm_market(market_type)
        with self._conn() as c:
            c.execute(
                "DELETE FROM favorite_group_members WHERE user_id=? AND symbol=? AND market_type=?",
                (self.user_id, symbol, mt),
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
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO favorite_group_members(group_id, symbol, user_id, market_type) VALUES (?,?,?,?)",
                        (gid, symbol, self.user_id, mt),
                    )
                except sqlite3.Error:
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

    def add_price_alert(
        self, symbol: str, kind: str, threshold: float | None, market_type: str = "BIST"
    ) -> PriceAlertRule:
        aid = uuid.uuid4().hex
        mt = _norm_market(market_type)
        rule = PriceAlertRule(alert_id=aid, symbol=symbol.upper(), kind=kind.upper(), threshold=threshold)
        with self._conn() as c:
            try:
                c.execute(
                    """
                    INSERT INTO favorite_price_alerts(alert_id, user_id, symbol, market_type, kind, threshold, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (aid, self.user_id, rule.symbol, mt, rule.kind, threshold, rule.created_at),
                )
            except sqlite3.Error:
                c.execute(
                    """
                    INSERT INTO favorite_price_alerts(alert_id, user_id, symbol, kind, threshold, active, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    """,
                    (aid, self.user_id, rule.symbol, rule.kind, threshold, rule.created_at),
                )
        return rule

    def list_price_alerts(self, symbol: str | None = None, market_type: str | None = None) -> list[PriceAlertRule]:
        q = "SELECT * FROM favorite_price_alerts WHERE user_id=? AND active=1"
        args: list = [self.user_id]
        if symbol:
            q += " AND symbol=?"
            args.append(symbol.upper())
        if market_type is not None:
            q += " AND market_type=?"
            args.append(_norm_market(market_type))
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

    def add_event(
        self,
        symbol: str,
        event_type: str,
        message: str,
        payload: dict | None = None,
        market_type: str = "BIST",
    ) -> None:
        mt = _norm_market(market_type)
        with self._conn() as c:
            try:
                c.execute(
                    """
                    INSERT INTO favorite_events(user_id, symbol, market_type, event_type, message, payload_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.user_id,
                        symbol.upper(),
                        mt,
                        event_type,
                        message,
                        json.dumps(payload or {}),
                        utc_now().isoformat(),
                    ),
                )
            except sqlite3.Error:
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

    def timeline(self, symbol: str, limit: int = 50, market_type: str | None = None) -> list[dict]:
        q = "SELECT * FROM favorite_events WHERE user_id=? AND symbol=?"
        args: list = [self.user_id, symbol.upper()]
        if market_type is not None:
            q += " AND market_type=?"
            args.append(_norm_market(market_type))
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def update_last_signal(
        self, symbol: str, signal: str, confidence: float, market_type: str = "BIST"
    ) -> str | None:
        """Returns previous signal if changed."""
        mt = _norm_market(market_type)
        fav = self.get(symbol, market_type=mt)
        prev = fav.last_ai_signal if fav else None
        with self._conn() as c:
            c.execute(
                "UPDATE favorites SET last_ai_signal=?, last_ai_confidence=?, updated_at=? "
                "WHERE user_id=? AND market_type=? AND symbol=?",
                (signal, confidence, utc_now().isoformat(), self.user_id, mt, symbol.upper()),
            )
        return prev

    def record_signal_outcome(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        outcome_pct: float | None = None,
        market_type: str = "BIST",
    ) -> None:
        mt = _norm_market(market_type)
        with self._conn() as c:
            try:
                c.execute(
                    """
                    INSERT INTO favorite_signal_stats(user_id, symbol, market_type, signal, confidence, outcome_pct, closed, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.user_id,
                        symbol.upper(),
                        mt,
                        signal,
                        confidence,
                        outcome_pct,
                        1 if outcome_pct is not None else 0,
                        utc_now().isoformat(),
                    ),
                )
            except sqlite3.Error:
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

    def performance(self, market_type: str | None = None) -> dict:
        q = "SELECT outcome_pct FROM favorite_signal_stats WHERE user_id=? AND closed=1 AND outcome_pct IS NOT NULL"
        args: list = [self.user_id]
        if market_type is not None:
            q += " AND market_type=?"
            args.append(_norm_market(market_type))
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
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
        mt = "BIST"
        try:
            mt = r["market_type"] or "BIST"
        except (IndexError, KeyError):
            mt = "BIST"
        with self._conn() as c:
            try:
                grows = c.execute(
                    """
                    SELECT g.name FROM favorite_group_members m
                    JOIN favorite_groups g ON g.group_id=m.group_id
                    WHERE m.user_id=? AND m.symbol=? AND m.market_type=?
                    """,
                    (r["user_id"], r["symbol"], mt),
                ).fetchall()
            except sqlite3.Error:
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
            market_type=mt,
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
