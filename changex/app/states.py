"""CHANGE X trade state machine — invalid transitions are rejected."""

from __future__ import annotations

from enum import Enum


class TradeState(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    OFFERED = "OFFERED"
    COUNTER_OFFERED = "COUNTER_OFFERED"
    ACCEPTED = "ACCEPTED"
    CONFIRMED = "CONFIRMED"
    IN_TRANSFER = "IN_TRANSFER"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


ALLOWED: dict[TradeState, set[TradeState]] = {
    TradeState.DRAFT: {TradeState.PENDING, TradeState.CANCELLED},
    TradeState.PENDING: {TradeState.OFFERED, TradeState.CANCELLED, TradeState.EXPIRED},
    TradeState.OFFERED: {
        TradeState.COUNTER_OFFERED,
        TradeState.ACCEPTED,
        TradeState.CANCELLED,
        TradeState.EXPIRED,
    },
    TradeState.COUNTER_OFFERED: {
        TradeState.OFFERED,
        TradeState.ACCEPTED,
        TradeState.CANCELLED,
        TradeState.EXPIRED,
    },
    TradeState.ACCEPTED: {TradeState.CONFIRMED, TradeState.CANCELLED, TradeState.DISPUTED},
    TradeState.CONFIRMED: {TradeState.IN_TRANSFER, TradeState.CANCELLED, TradeState.DISPUTED},
    TradeState.IN_TRANSFER: {TradeState.DELIVERED, TradeState.DISPUTED, TradeState.CANCELLED},
    TradeState.DELIVERED: {TradeState.COMPLETED, TradeState.DISPUTED},
    TradeState.COMPLETED: set(),
    TradeState.CANCELLED: set(),
    TradeState.DISPUTED: {TradeState.CANCELLED, TradeState.CONFIRMED},
    TradeState.EXPIRED: set(),
}


class InvalidTransition(Exception):
    pass


def transition(current: TradeState, target: TradeState) -> TradeState:
    allowed = ALLOWED.get(current, set())
    if target not in allowed:
        raise InvalidTransition(f"{current.value} -> {target.value} geçersiz")
    return target
