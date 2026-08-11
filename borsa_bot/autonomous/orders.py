"""Order state machine + idempotent client_order_id helpers."""

from __future__ import annotations

from enum import Enum
from hashlib import sha1
from typing import Any

from config.models import utc_now


class OrderState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SHADOW = "SHADOW"  # would-have-traded; never sent


_ALLOWED: dict[OrderState, set[OrderState]] = {
    OrderState.CREATED: {OrderState.VALIDATED, OrderState.REJECTED, OrderState.BLOCKED, OrderState.SHADOW, OrderState.FAILED},
    OrderState.VALIDATED: {OrderState.SUBMITTED, OrderState.REJECTED, OrderState.BLOCKED, OrderState.FAILED, OrderState.SHADOW},
    OrderState.SUBMITTED: {
        OrderState.ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.FAILED,
    },
    OrderState.ACKNOWLEDGED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.FAILED,
    },
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELLED, OrderState.FAILED},
    OrderState.FILLED: set(),
    OrderState.REJECTED: set(),
    OrderState.CANCELLED: set(),
    OrderState.FAILED: set(),
    OrderState.BLOCKED: set(),
    OrderState.SHADOW: set(),
}


def transition(current: OrderState, new: OrderState) -> OrderState:
    allowed = _ALLOWED.get(current, set())
    if new == current:
        return current
    if new not in allowed:
        raise ValueError(f"illegal order transition {current.value} → {new.value}")
    return new


def make_client_order_id(
    *,
    market: str,
    symbol: str,
    side: str,
    signal: str,
    cycle_id: str,
    window_minutes: int = 15,
) -> str:
    """Deterministic idempotency key for broker/paper submit (not a secret)."""
    bucket = int(utc_now().timestamp() // max(60, window_minutes * 60))
    raw = f"{market}|{symbol.upper()}|{side.upper()}|{signal}|{cycle_id}|{bucket}"
    digest = sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"ATE-{symbol.upper()}-{digest}"


def order_record(
    *,
    client_order_id: str,
    state: OrderState,
    symbol: str,
    side: str,
    qty: float | None = None,
    price: float | None = None,
    broker_order_id: str | None = None,
    message: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "client_order_id": client_order_id,
        "state": state.value,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "price": price,
        "broker_order_id": broker_order_id,
        "message": message,
        "ts": utc_now().isoformat(),
        **(extra or {}),
    }
