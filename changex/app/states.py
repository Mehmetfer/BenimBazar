"""CHANGE X listing + trade state machines."""

from __future__ import annotations

from enum import Enum


class ListingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESERVED = "RESERVED"
    TRADED = "TRADED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


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
    TradeState.DRAFT: {TradeState.PENDING, TradeState.OFFERED, TradeState.CANCELLED},
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
    TradeState.ACCEPTED: {
        TradeState.CONFIRMED,
        TradeState.CANCELLED,
        TradeState.DISPUTED,
    },
    TradeState.CONFIRMED: {
        TradeState.IN_TRANSFER,
        TradeState.CANCELLED,
        TradeState.DISPUTED,
    },
    TradeState.IN_TRANSFER: {
        TradeState.DELIVERED,
        TradeState.DISPUTED,
        TradeState.CANCELLED,
    },
    TradeState.DELIVERED: {TradeState.COMPLETED, TradeState.DISPUTED},
    TradeState.COMPLETED: set(),
    TradeState.CANCELLED: set(),
    TradeState.DISPUTED: {TradeState.CANCELLED, TradeState.CONFIRMED},
    TradeState.EXPIRED: set(),
}


class InvalidTransition(Exception):
    pass


def can_transition(current: TradeState, target: TradeState) -> bool:
    return target in ALLOWED.get(current, set())


def transition(current: TradeState, target: TradeState) -> TradeState:
    if not can_transition(current, target):
        raise InvalidTransition(f"{current.value} -> {target.value} geçersiz")
    return target


OFFERABLE_LISTING = {ListingStatus.ACTIVE}
RESERVABLE_FROM = {ListingStatus.ACTIVE}
RELEASE_TO_ACTIVE_FROM = {ListingStatus.RESERVED}
