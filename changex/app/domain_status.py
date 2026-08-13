"""CHANGE X dual-domain states: moderation vs inventory (Exchange Graph V1).

Legacy `ListingStatus` remains for Trust & Safety / trade engine compatibility.
New code should prefer ModerationStatus + InventoryStatus.
"""

from __future__ import annotations

from enum import Enum

# Re-export / extend — keep legacy ListingStatus transitions intact via import from states
# This module defines the split domain model.


class ModerationStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_MODERATION = "PENDING_MODERATION"
    AI_REVIEW = "AI_REVIEW"
    ADMIN_REVIEW = "ADMIN_REVIEW"
    MODERATION_UNAVAILABLE = "MODERATION_UNAVAILABLE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDIT_REQUIRED = "EDIT_REQUIRED"
    ESCALATED = "ESCALATED"
    SUSPENDED = "SUSPENDED"


class InventoryStatus(str, Enum):
    """Trade/inventory lifecycle — orthogonal to moderation."""

    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    TRADED = "TRADED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TradePreference(str, Enum):
    DIRECT_ONLY = "DIRECT_ONLY"
    CHAIN_ALLOWED = "CHAIN_ALLOWED"


# Moderation states that are still "in review"
MODERATION_PENDING = {
    ModerationStatus.DRAFT,
    ModerationStatus.PENDING_MODERATION,
    ModerationStatus.AI_REVIEW,
    ModerationStatus.ADMIN_REVIEW,
    ModerationStatus.MODERATION_UNAVAILABLE,
    ModerationStatus.EDIT_REQUIRED,
    ModerationStatus.ESCALATED,
}

# Inventory states that block matching / chain candidacy
INVENTORY_BLOCKED = {
    InventoryStatus.RESERVED,
    InventoryStatus.TRADED,
    InventoryStatus.CANCELLED,
    InventoryStatus.EXPIRED,
}

# Planned future chain event kinds (not emitted in Exchange Graph V1)
PLANNED_CHAIN_EVENTS = (
    "MATCH_CANDIDATE_CREATED",
    "MATCH_CANDIDATE_REJECTED",
    "CHAIN_CANDIDATE_CREATED",
    "CHAIN_CANCELLED",
    "ASSET_LOCKED",
    "ASSET_UNLOCKED",
    "CHAIN_COMMITTED",
)


def split_from_legacy_status(status: str) -> tuple[ModerationStatus, InventoryStatus]:
    """Derive dual statuses from legacy combined `status` column."""
    s = (status or "").upper()
    if s in {"RESERVED"}:
        return ModerationStatus.APPROVED, InventoryStatus.RESERVED
    if s in {"TRADED"}:
        return ModerationStatus.APPROVED, InventoryStatus.TRADED
    if s in {"CANCELLED"}:
        return ModerationStatus.REJECTED, InventoryStatus.CANCELLED
    if s in {"EXPIRED"}:
        return ModerationStatus.APPROVED, InventoryStatus.EXPIRED
    if s in {"ACTIVE", "APPROVED"}:
        return ModerationStatus.APPROVED, InventoryStatus.AVAILABLE
    if s in {"SUSPENDED"}:
        return ModerationStatus.SUSPENDED, InventoryStatus.AVAILABLE
    if s in {"REJECTED"}:
        return ModerationStatus.REJECTED, InventoryStatus.AVAILABLE
    if s in {"EDIT_REQUIRED"}:
        return ModerationStatus.EDIT_REQUIRED, InventoryStatus.AVAILABLE
    if s in {"ESCALATED"}:
        return ModerationStatus.ESCALATED, InventoryStatus.AVAILABLE
    if s in {"ADMIN_REVIEW"}:
        return ModerationStatus.ADMIN_REVIEW, InventoryStatus.AVAILABLE
    if s in {"AI_REVIEW"}:
        return ModerationStatus.AI_REVIEW, InventoryStatus.AVAILABLE
    if s in {"MODERATION_UNAVAILABLE"}:
        return ModerationStatus.MODERATION_UNAVAILABLE, InventoryStatus.AVAILABLE
    if s in {"DRAFT"}:
        return ModerationStatus.DRAFT, InventoryStatus.AVAILABLE
    return ModerationStatus.PENDING_MODERATION, InventoryStatus.AVAILABLE


def legacy_status_from_split(
    moderation: ModerationStatus, inventory: InventoryStatus
) -> str:
    """Project dual domain back to legacy single status for API/engine compat."""
    if inventory == InventoryStatus.RESERVED:
        return "RESERVED"
    if inventory == InventoryStatus.TRADED:
        return "TRADED"
    if inventory == InventoryStatus.CANCELLED:
        return "CANCELLED"
    if inventory == InventoryStatus.EXPIRED:
        return "EXPIRED"
    if moderation == ModerationStatus.APPROVED:
        return "APPROVED"
    return moderation.value
