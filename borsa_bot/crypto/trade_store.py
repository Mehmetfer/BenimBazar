"""Persistent Paribu public-trade store → OHLCV accumulation (no candle API).

Official Paribu REST has no OHLCV endpoint; /trades max limit=20 (API 4001).
Bars grow only from real trades (REST + WS). Never invent candles.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config.models import Bar
from config.settings import ROOT
from crypto.ohlcv import aggregate_trades_to_bars
from crypto.rest import RawTrade
from data.integrity import DataSourceKind


DEFAULT_DB = ROOT / "database" / "crypto_trades.db"


class CryptoTradeStore:
    """SQLite-backed trade buffer for CRYPTO market_type only."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS crypto_trades (
                        market_type TEXT NOT NULL DEFAULT 'CRYPTO',
                        provider TEXT NOT NULL DEFAULT 'paribu',
                        symbol TEXT NOT NULL,
                        provider_symbol TEXT NOT NULL,
                        ts_utc TEXT NOT NULL,
                        price REAL NOT NULL,
                        amount REAL NOT NULL,
                        side TEXT,
                        source_kind TEXT NOT NULL DEFAULT 'LIVE',
                        UNIQUE(symbol, ts_utc, price, amount, side)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_crypto_trades_sym_ts ON crypto_trades(symbol, ts_utc)"
                )

    def add_trades(
        self,
        app_symbol: str,
        trades: Iterable[RawTrade],
        *,
        provider_symbol: str,
        provider: str = "paribu",
    ) -> int:
        rows = []
        for t in trades:
            if t.price <= 0 or t.amount < 0:
                continue
            ts = t.time.astimezone(timezone.utc).isoformat()
            rows.append(
                (
                    "CRYPTO",
                    provider,
                    app_symbol.upper(),
                    provider_symbol.lower(),
                    ts,
                    float(t.price),
                    float(t.amount),
                    (t.side or "").lower(),
                    DataSourceKind.LIVE.value,
                )
            )
        if not rows:
            return 0
        with self._lock:
            with self._conn() as conn:
                before = conn.total_changes
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO crypto_trades
                    (market_type, provider, symbol, provider_symbol, ts_utc, price, amount, side, source_kind)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                return max(0, conn.total_changes - before)

    def load_trades(self, app_symbol: str, *, limit: int = 50_000) -> list[RawTrade]:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    """
                    SELECT ts_utc, price, amount, side FROM crypto_trades
                    WHERE market_type='CRYPTO' AND symbol=?
                    ORDER BY ts_utc DESC
                    LIMIT ?
                    """,
                    (app_symbol.upper(), int(limit)),
                )
                rows = cur.fetchall()
        out: list[RawTrade] = []
        for ts_utc, price, amount, side in reversed(rows):
            try:
                ts = datetime.fromisoformat(str(ts_utc).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            out.append(RawTrade(price=float(price), amount=float(amount), time=ts, side=str(side or "")))
        return out

    def bars(
        self,
        app_symbol: str,
        *,
        timeframe: str = "15m",
        lookback: int = 240,
        provider: str = "paribu",
    ) -> list[Bar]:
        trades = self.load_trades(app_symbol)
        return aggregate_trades_to_bars(trades, symbol=app_symbol, timeframe=timeframe, provider=provider)[
            -lookback:
        ]

    def trade_count(self, app_symbol: str) -> int:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM crypto_trades WHERE market_type='CRYPTO' AND symbol=?",
                    (app_symbol.upper(),),
                )
                return int(cur.fetchone()[0])

    def stats(self) -> dict:
        with self._lock:
            with self._conn() as conn:
                n = conn.execute("SELECT COUNT(*) FROM crypto_trades WHERE market_type='CRYPTO'").fetchone()[0]
                syms = conn.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM crypto_trades WHERE market_type='CRYPTO'"
                ).fetchone()[0]
        return {"stored_trades": int(n), "symbols_with_trades": int(syms), "path": str(self.path)}
