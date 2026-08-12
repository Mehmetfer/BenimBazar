"""Unknown order state — never assume failure after submit without ack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class OrderCertainty(str, Enum):
    KNOWN_FILLED = "KNOWN_FILLED"
    KNOWN_REJECTED = "KNOWN_REJECTED"
    KNOWN_CANCELED = "KNOWN_CANCELED"
    UNKNOWN = "UNKNOWN"
    NOT_SENT = "NOT_SENT"


@dataclass
class UnknownOrderRecord:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    certainty: OrderCertainty = OrderCertainty.UNKNOWN
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_query_at: str | None = None
    broker_status: str | None = None
    notes: list[str] = field(default_factory=list)

    def blocks_new_orders_on_symbol(self) -> bool:
        return self.certainty is OrderCertainty.UNKNOWN


class UnknownOrderRegistry:
    def __init__(self) -> None:
        self._orders: dict[str, UnknownOrderRecord] = {}

    def mark_unknown(self, client_order_id: str, *, symbol: str, side: str, quantity: float) -> UnknownOrderRecord:
        rec = UnknownOrderRecord(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            certainty=OrderCertainty.UNKNOWN,
        )
        rec.notes.append("submit_timeout_or_lost_response")
        self._orders[client_order_id] = rec
        return rec

    def resolve_from_broker(self, client_order_id: str, broker_status: str | None) -> UnknownOrderRecord | None:
        rec = self._orders.get(client_order_id)
        if rec is None:
            return None
        rec.last_query_at = datetime.now(timezone.utc).isoformat()
        st = (broker_status or "UNKNOWN").upper()
        rec.broker_status = st
        if st in {"FILLED", "PARTIALLY_FILLED"}:
            rec.certainty = OrderCertainty.KNOWN_FILLED
        elif st in {"REJECTED", "BLOCKED", "FAILED"}:
            rec.certainty = OrderCertainty.KNOWN_REJECTED
        elif st in {"CANCELED", "CANCELLED"}:
            rec.certainty = OrderCertainty.KNOWN_CANCELED
        else:
            rec.certainty = OrderCertainty.UNKNOWN
            rec.notes.append(f"still_unknown:{st}")
        return rec

    def has_blocking_unknown(self, symbol: str | None = None) -> tuple[bool, str]:
        for rec in self._orders.values():
            if rec.certainty is OrderCertainty.UNKNOWN:
                if symbol is None or rec.symbol.upper() == symbol.upper():
                    return True, f"UNKNOWN_ORDER:{rec.client_order_id}:{rec.symbol}"
        return False, ""

    def open_unknowns(self) -> list[UnknownOrderRecord]:
        return [r for r in self._orders.values() if r.certainty is OrderCertainty.UNKNOWN]
