"""CHANGE X listing + trade state machines (Trust & Safety V1)."""

from __future__ import annotations

from enum import Enum


class ListingStatus(str, Enum):
    """Listing lifecycle including moderation + trade locks."""

    DRAFT = "DRAFT"
    PENDING_MODERATION = "PENDING_MODERATION"
    AI_REVIEW = "AI_REVIEW"
    ADMIN_REVIEW = "ADMIN_REVIEW"
    MODERATION_UNAVAILABLE = "MODERATION_UNAVAILABLE"
    APPROVED = "APPROVED"
    # Legacy alias kept for migration/read compatibility — treat as APPROVED.
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    EDIT_REQUIRED = "EDIT_REQUIRED"
    ESCALATED = "ESCALATED"
    SUSPENDED = "SUSPENDED"
    RESERVED = "RESERVED"
    TRADED = "TRADED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AiModerationResult(str, Enum):
    SAFE = "SAFE"
    REVIEW = "REVIEW"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class ModerationDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_EDIT = "REQUEST_EDIT"
    ESCALATE = "ESCALATE"
    SUSPEND_USER = "SUSPEND_USER"
    DELETE = "DELETE"  # soft-cancel listing from queue / panel


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class UserRole(str, Enum):
    USER = "user"
    MODERATOR = "moderator"  # onaycı — onay kutusunda karar verir
    ADMIN = "admin"  # yönetici — kuyruk + görev atama
    SUPERADMIN = "superadmin"  # sınırsız


# Staff who may act on moderation queue (approve / reject / edit / delete)
MODERATION_STAFF_ROLES = {
    UserRole.MODERATOR.value,
    UserRole.ADMIN.value,
    UserRole.SUPERADMIN.value,
}

# Roles Superadmin may assign to others
ASSIGNABLE_ROLES = {
    UserRole.USER.value,
    UserRole.MODERATOR.value,
    UserRole.ADMIN.value,
}


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


LISTING_TRANSITIONS: dict[ListingStatus, set[ListingStatus]] = {
    ListingStatus.DRAFT: {ListingStatus.PENDING_MODERATION, ListingStatus.CANCELLED},
    ListingStatus.PENDING_MODERATION: {
        ListingStatus.AI_REVIEW,
        ListingStatus.ADMIN_REVIEW,
        ListingStatus.MODERATION_UNAVAILABLE,
        ListingStatus.APPROVED,  # staff may approve from pending
        ListingStatus.REJECTED,
        ListingStatus.EDIT_REQUIRED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.AI_REVIEW: {
        ListingStatus.ADMIN_REVIEW,
        ListingStatus.MODERATION_UNAVAILABLE,
        ListingStatus.APPROVED,
        ListingStatus.REJECTED,  # hard safety reject (e.g. CSAM)
        ListingStatus.EDIT_REQUIRED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.ADMIN_REVIEW: {
        ListingStatus.APPROVED,
        ListingStatus.REJECTED,
        ListingStatus.EDIT_REQUIRED,
        ListingStatus.ESCALATED,
        ListingStatus.SUSPENDED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.ESCALATED: {
        ListingStatus.APPROVED,
        ListingStatus.REJECTED,
        ListingStatus.EDIT_REQUIRED,
        ListingStatus.SUSPENDED,
        ListingStatus.ADMIN_REVIEW,
        ListingStatus.CANCELLED,
    },
    ListingStatus.MODERATION_UNAVAILABLE: {
        ListingStatus.ADMIN_REVIEW,
        ListingStatus.APPROVED,
        ListingStatus.REJECTED,
        ListingStatus.PENDING_MODERATION,
        ListingStatus.EDIT_REQUIRED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.APPROVED: {
        ListingStatus.PENDING_MODERATION,  # critical edit re-moderation
        ListingStatus.RESERVED,
        ListingStatus.SUSPENDED,
        ListingStatus.REJECTED,  # emergency takedown
        ListingStatus.CANCELLED,
        ListingStatus.EXPIRED,
        ListingStatus.EDIT_REQUIRED,
    },
    ListingStatus.ACTIVE: {  # legacy
        ListingStatus.APPROVED,
        ListingStatus.PENDING_MODERATION,
        ListingStatus.RESERVED,
        ListingStatus.CANCELLED,
        ListingStatus.EXPIRED,
        ListingStatus.SUSPENDED,
    },
    ListingStatus.REJECTED: {ListingStatus.PENDING_MODERATION, ListingStatus.CANCELLED},
    ListingStatus.EDIT_REQUIRED: {
        ListingStatus.PENDING_MODERATION,
        ListingStatus.APPROVED,
        ListingStatus.REJECTED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.SUSPENDED: {ListingStatus.ADMIN_REVIEW, ListingStatus.CANCELLED},
    ListingStatus.RESERVED: {
        ListingStatus.APPROVED,  # release after cancel
        ListingStatus.TRADED,
        ListingStatus.CANCELLED,
    },
    ListingStatus.TRADED: set(),
    ListingStatus.CANCELLED: set(),
    ListingStatus.EXPIRED: set(),
}


class InvalidTransition(Exception):
    pass


def can_transition(current: TradeState, target: TradeState) -> bool:
    return target in ALLOWED.get(current, set())


def transition(current: TradeState, target: TradeState) -> TradeState:
    if not can_transition(current, target):
        raise InvalidTransition(f"{current.value} -> {target.value} geçersiz")
    return target


def can_listing_transition(current: ListingStatus, target: ListingStatus) -> bool:
    return target in LISTING_TRANSITIONS.get(current, set())


def listing_transition(current: ListingStatus, target: ListingStatus) -> ListingStatus:
    if not can_listing_transition(current, target):
        raise InvalidTransition(f"listing {current.value} -> {target.value} geçersiz")
    return target


def normalize_listing_status(raw: str | ListingStatus | None) -> ListingStatus:
    if raw is None:
        return ListingStatus.PENDING_MODERATION
    if isinstance(raw, ListingStatus):
        status = raw
    else:
        status = ListingStatus(str(raw).upper())
    if status == ListingStatus.ACTIVE:
        return ListingStatus.APPROVED
    return status


# Public marketplace + offers require Superadmin-approved listings.
PUBLIC_LISTING = {ListingStatus.APPROVED, ListingStatus.ACTIVE}
OFFERABLE_LISTING = {ListingStatus.APPROVED, ListingStatus.ACTIVE}
RESERVABLE_FROM = {ListingStatus.APPROVED, ListingStatus.ACTIVE}
RELEASE_TO_ACTIVE_FROM = {ListingStatus.RESERVED}
RELEASE_TO_APPROVED = ListingStatus.APPROVED

POLICY_VERSION = "CHANGE_X_SAFETY_V1"
