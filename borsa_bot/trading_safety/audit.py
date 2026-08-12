"""Append-only trading audit — fail-closed if write fails before real submit."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AuditRecord:
    timestamp: str
    symbol: str
    market_data_timestamp: str | None
    signal: str
    strategy_decision: str
    risk_decision: str
    provider_state: str
    portfolio_state: str
    order_intent: str
    idempotency_key: str
    order_id: str | None = None
    execution_result: str = ""
    failure_reason: str = ""
    reconciliation_state: str = ""
    mode: str = "PAPER"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradingAuditLog:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or Path(__file__).resolve().parents[1] / "logs" / "trading_audit.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_audit (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  symbol TEXT,
                  payload TEXT NOT NULL
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def append(self, record: AuditRecord) -> bool:
        """Return False if persistence failed (caller must NOT send real orders)."""
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO trading_audit(ts, symbol, payload) VALUES (?,?,?)",
                    (record.timestamp, record.symbol, json.dumps(record.to_dict(), ensure_ascii=False)),
                )
            return True
        except Exception:  # noqa: BLE001
            return False

    def count(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) FROM trading_audit").fetchone()
        return int(row[0] if row else 0)


def new_audit(
    *,
    symbol: str,
    signal: str,
    strategy_decision: str,
    risk_decision: str,
    provider_state: str,
    portfolio_state: str,
    order_intent: str,
    idempotency_key: str,
    mode: str = "PAPER",
    market_data_timestamp: str | None = None,
) -> AuditRecord:
    return AuditRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol,
        market_data_timestamp=market_data_timestamp,
        signal=signal,
        strategy_decision=strategy_decision,
        risk_decision=risk_decision,
        provider_state=provider_state,
        portfolio_state=portfolio_state,
        order_intent=order_intent,
        idempotency_key=idempotency_key,
        mode=mode,
    )
