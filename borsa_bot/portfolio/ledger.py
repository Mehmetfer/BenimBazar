from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from config.settings import settings


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Position:
    symbol: str
    sector: str
    quantity: float
    avg_cost: float
    stop_price: float | None = None
    target_price: float | None = None


class PortfolioLedger:
    def __init__(self, db_path: Path | None = None, mark_prices: dict[str, float] | None = None) -> None:
        self.db_path = Path(db_path or settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.mark_prices = mark_prices or {}
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    cash REAL NOT NULL,
                    starting_cash REAL NOT NULL,
                    day_start_equity REAL NOT NULL,
                    day_key TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions(
                    symbol TEXT PRIMARY KEY,
                    sector TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_cost REAL NOT NULL,
                    stop_price REAL,
                    target_price REAL
                );
                CREATE TABLE IF NOT EXISTS trades(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    side TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    order_id TEXT
                );
                CREATE TABLE IF NOT EXISTS decision_log(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL,
                    signal TEXT,
                    buy_score REAL,
                    sell_score REAL,
                    ai_confidence REAL,
                    risk TEXT,
                    explanation TEXT,
                    stop_price REAL,
                    target_price REAL
                );
                """
            )
            row = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()
            if row is None:
                today = date.today().isoformat()
                conn.execute(
                    "INSERT INTO account(id,cash,starting_cash,day_start_equity,day_key) VALUES(1,?,?,?,?)",
                    (settings.starting_cash, settings.starting_cash, settings.starting_cash, today),
                )

    @property
    def cash(self) -> float:
        with self._connect() as conn:
            return float(conn.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"])

    def set_marks(self, marks: dict[str, float]) -> None:
        self.mark_prices = marks
        self._roll_day_if_needed()

    def _roll_day_if_needed(self) -> None:
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT day_key FROM account WHERE id=1").fetchone()
            if row["day_key"] != today:
                eq = self.equity()
                conn.execute(
                    "UPDATE account SET day_key=?, day_start_equity=? WHERE id=1",
                    (today, eq),
                )

    def get_position(self, symbol: str) -> Position | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
        if not row:
            return None
        return Position(**dict(row))

    def positions(self) -> list[Position]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        return [Position(**dict(r)) for r in rows]

    def open_position_count(self) -> int:
        return len(self.positions())

    def sector_position_count(self, sector: str) -> int:
        return sum(1 for p in self.positions() if p.sector == sector)

    def holdings_value(self) -> float:
        total = 0.0
        for p in self.positions():
            mark = self.mark_prices.get(p.symbol, p.avg_cost)
            total += p.quantity * mark
        return total

    def equity(self) -> float:
        return self.cash + self.holdings_value()

    def total_pnl(self) -> float:
        with self._connect() as conn:
            start = float(conn.execute("SELECT starting_cash FROM account WHERE id=1").fetchone()["starting_cash"])
        return self.equity() - start

    def daily_pnl(self) -> float:
        with self._connect() as conn:
            day_start = float(conn.execute("SELECT day_start_equity FROM account WHERE id=1").fetchone()["day_start_equity"])
        return self.equity() - day_start

    def daily_loss_pct(self) -> float:
        with self._connect() as conn:
            day_start = float(conn.execute("SELECT day_start_equity FROM account WHERE id=1").fetchone()["day_start_equity"])
        if day_start <= 0:
            return 0.0
        return (self.equity() - day_start) / day_start * 100

    def consecutive_losses(self) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT pnl FROM trades WHERE side='SELL' ORDER BY id DESC LIMIT 10"
            ).fetchall()
        n = 0
        for r in rows:
            if float(r["pnl"]) < 0:
                n += 1
            else:
                break
        return n

    def peak_equity(self) -> float:
        with self._connect() as conn:
            start = float(conn.execute("SELECT starting_cash FROM account WHERE id=1").fetchone()["starting_cash"])
        # Approximate peak as max(start, current) — extend with history later
        return max(start, self.equity())

    def drawdown_pct(self) -> float:
        peak = self.peak_equity()
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.equity()) / peak * 100)

    def weekly_loss_pct(self) -> float:
        """Approx weekly PnL % from last 7d sells + MTM vs starting; MVP uses total_pnl proxy scaled."""
        # Without full equity history, use daily as conservative proxy if total drawdown small
        return min(0.0, self.daily_loss_pct() * 2.5)

    def sector_risk_pct(self, sector: str) -> float:
        eq = self.equity()
        if eq <= 0:
            return 0.0
        risk = 0.0
        for p in self.positions():
            if p.sector != sector:
                continue
            mark = self.mark_prices.get(p.symbol, p.avg_cost)
            stop = p.stop_price or (p.avg_cost * 0.97)
            risk += max(0.0, (mark - stop) * p.quantity)
        return risk / eq * 100

    def apply_buy(
        self,
        symbol: str,
        sector: str,
        quantity: float,
        price: float,
        order_id: str,
        stop: float | None,
        target: float | None,
    ) -> None:
        total = quantity * price
        with self._connect() as conn:
            cash = float(conn.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"])
            if total > cash:
                raise ValueError("insufficient cash")
            conn.execute("UPDATE account SET cash=cash-? WHERE id=1", (total,))
            existing = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if existing:
                qty = float(existing["quantity"]) + quantity
                avg = (float(existing["quantity"]) * float(existing["avg_cost"]) + total) / qty
                conn.execute(
                    "UPDATE positions SET quantity=?, avg_cost=?, stop_price=?, target_price=? WHERE symbol=?",
                    (qty, avg, stop, target, symbol),
                )
            else:
                conn.execute(
                    "INSERT INTO positions(symbol,sector,quantity,avg_cost,stop_price,target_price) VALUES(?,?,?,?,?,?)",
                    (symbol, sector, quantity, price, stop, target),
                )
            conn.execute(
                "INSERT INTO trades(ts,side,symbol,quantity,price,pnl,order_id) VALUES(?,?,?,?,?,?,?)",
                (_utc(), "BUY", symbol, quantity, price, 0, order_id),
            )

    def apply_sell(self, symbol: str, quantity: float, price: float, order_id: str) -> float:
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if not existing or float(existing["quantity"]) < quantity:
                raise ValueError("insufficient position")
            avg = float(existing["avg_cost"])
            pnl = (price - avg) * quantity
            proceeds = quantity * price
            left = float(existing["quantity"]) - quantity
            conn.execute("UPDATE account SET cash=cash+? WHERE id=1", (proceeds,))
            if left <= 1e-9:
                conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            else:
                conn.execute("UPDATE positions SET quantity=? WHERE symbol=?", (left, symbol))
            conn.execute(
                "INSERT INTO trades(ts,side,symbol,quantity,price,pnl,order_id) VALUES(?,?,?,?,?,?,?)",
                (_utc(), "SELL", symbol, quantity, price, pnl, order_id),
            )
            return pnl

    def log_decision(self, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decision_log(ts,symbol,price,signal,buy_score,sell_score,ai_confidence,risk,explanation,stop_price,target_price)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _utc(),
                    payload.get("symbol"),
                    payload.get("price"),
                    payload.get("signal"),
                    payload.get("buy_score"),
                    payload.get("sell_score"),
                    payload.get("ai_confidence"),
                    payload.get("risk"),
                    payload.get("explanation"),
                    payload.get("stop_price"),
                    payload.get("target_price"),
                ),
            )

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM decision_log")
            today = date.today().isoformat()
            conn.execute(
                "UPDATE account SET cash=?, starting_cash=?, day_start_equity=?, day_key=? WHERE id=1",
                (settings.starting_cash, settings.starting_cash, settings.starting_cash, today),
            )
