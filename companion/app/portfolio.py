from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, DB_PATH, STARTING_CASH
from .market import get_price


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float


@dataclass
class Trade:
    id: int
    side: str
    symbol: str
    quantity: float
    price: float
    total: float
    created_at: str


class Portfolio:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity REAL NOT NULL,
                    avg_cost REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    side TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    total REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            row = conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO account(id, cash) VALUES (1, ?)",
                    (STARTING_CASH,),
                )

    def cash(self) -> float:
        with self._connect() as conn:
            return float(conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])

    def positions(self) -> list[Position]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT symbol, quantity, avg_cost FROM positions WHERE quantity > 0 ORDER BY symbol"
            ).fetchall()
        return [Position(**dict(r)) for r in rows]

    def trades(self, limit: int = 20) -> list[Trade]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, side, symbol, quantity, price, total, created_at
                FROM trades ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [Trade(**dict(r)) for r in rows]

    def snapshot(self) -> dict:
        positions = []
        holdings_value = 0.0
        for pos in self.positions():
            mark = get_price(pos.symbol) or pos.avg_cost
            value = pos.quantity * mark
            pnl = (mark - pos.avg_cost) * pos.quantity
            pnl_pct = ((mark - pos.avg_cost) / pos.avg_cost) * 100 if pos.avg_cost else 0
            holdings_value += value
            positions.append(
                {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_cost": round(pos.avg_cost, 2),
                    "price": round(mark, 2),
                    "value": round(value, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                }
            )
        cash = self.cash()
        equity = cash + holdings_value
        return {
            "cash": round(cash, 2),
            "holdings_value": round(holdings_value, 2),
            "equity": round(equity, 2),
            "pnl": round(equity - STARTING_CASH, 2),
            "positions": positions,
            "trades": [
                {
                    "id": t.id,
                    "side": t.side,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "price": t.price,
                    "total": t.total,
                    "created_at": t.created_at,
                }
                for t in self.trades()
            ],
        }

    def buy(self, symbol: str, quantity: float) -> dict:
        symbol = symbol.strip().upper()
        quantity = float(quantity)
        if quantity <= 0:
            raise ValueError("Miktar 0'dan büyük olmalı.")
        price = get_price(symbol)
        if price is None:
            raise ValueError(f"Bilinmeyen hisse: {symbol}")
        total = round(price * quantity, 2)
        cash = self.cash()
        if total > cash:
            raise ValueError(f"Yetersiz bakiye. Gerekli: {total:.2f} TL, nakit: {cash:.2f} TL")

        with self._connect() as conn:
            conn.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (total,))
            existing = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if existing:
                new_qty = float(existing["quantity"]) + quantity
                new_cost = (
                    (float(existing["quantity"]) * float(existing["avg_cost"])) + total
                ) / new_qty
                conn.execute(
                    "UPDATE positions SET quantity = ?, avg_cost = ? WHERE symbol = ?",
                    (new_qty, new_cost, symbol),
                )
            else:
                conn.execute(
                    "INSERT INTO positions(symbol, quantity, avg_cost) VALUES (?, ?, ?)",
                    (symbol, quantity, price),
                )
            conn.execute(
                """
                INSERT INTO trades(side, symbol, quantity, price, total, created_at)
                VALUES ('BUY', ?, ?, ?, ?, ?)
                """,
                (symbol, quantity, price, total, _utc_now()),
            )
        return {"ok": True, "side": "BUY", "symbol": symbol, "quantity": quantity, "price": price, "total": total}

    def sell(self, symbol: str, quantity: float) -> dict:
        symbol = symbol.strip().upper()
        quantity = float(quantity)
        if quantity <= 0:
            raise ValueError("Miktar 0'dan büyük olmalı.")
        price = get_price(symbol)
        if price is None:
            raise ValueError(f"Bilinmeyen hisse: {symbol}")

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if not existing or float(existing["quantity"]) < quantity:
                have = float(existing["quantity"]) if existing else 0
                raise ValueError(f"Yetersiz lot. Elinde: {have}")
            total = round(price * quantity, 2)
            left = float(existing["quantity"]) - quantity
            conn.execute("UPDATE account SET cash = cash + ? WHERE id = 1", (total,))
            if left <= 1e-9:
                conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            else:
                conn.execute(
                    "UPDATE positions SET quantity = ? WHERE symbol = ?",
                    (left, symbol),
                )
            conn.execute(
                """
                INSERT INTO trades(side, symbol, quantity, price, total, created_at)
                VALUES ('SELL', ?, ?, ?, ?, ?)
                """,
                (symbol, quantity, price, total, _utc_now()),
            )
        return {"ok": True, "side": "SELL", "symbol": symbol, "quantity": quantity, "price": price, "total": total}

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM positions")
            conn.execute("UPDATE account SET cash = ? WHERE id = 1", (STARTING_CASH,))
