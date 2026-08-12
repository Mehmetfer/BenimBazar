"""Matchability gates — APPROVED + AVAILABLE + opt-in. No Chain algorithm."""

from __future__ import annotations

from typing import Any

from ..domain_status import (
    INVENTORY_BLOCKED,
    InventoryStatus,
    ModerationStatus,
    TradePreference,
    split_from_legacy_status,
)
from .config import CHANGE_CHAIN_ENABLED, change_chain_enabled


def _moderation_of(row: dict[str, Any]) -> ModerationStatus:
    raw = row.get("moderation_status")
    if raw:
        return ModerationStatus(str(raw).upper())
    mod, _ = split_from_legacy_status(str(row.get("status") or ""))
    return mod


def _inventory_of(row: dict[str, Any]) -> InventoryStatus:
    raw = row.get("inventory_status")
    if raw:
        return InventoryStatus(str(raw).upper())
    _, inv = split_from_legacy_status(str(row.get("status") or ""))
    return inv


def is_public_matchable(row: dict[str, Any]) -> bool:
    """Listing can appear as a direct-match candidate source/target (not chain)."""
    mod = _moderation_of(row)
    inv = _inventory_of(row)
    if mod != ModerationStatus.APPROVED:
        return False
    if inv != InventoryStatus.AVAILABLE:
        return False
    if mod == ModerationStatus.SUSPENDED:
        return False
    return True


def is_chain_candidate(row: dict[str, Any], *, user_pref: str | None = None) -> bool:
    """
    Chain candidacy gate (algorithm NOT run in Exchange Graph V1).

    Requires:
    - moderation APPROVED
    - inventory AVAILABLE
    - listing.chain_opt_in
    - trade_preference CHAIN_ALLOWED (listing or user)
    - feature flag does not grant matching — only allows preference storage;
      when flag false, still report structural eligibility separately.
    """
    if not is_public_matchable(row):
        return False
    if not bool(int(row.get("chain_opt_in") or 0)):
        return False
    pref = (row.get("trade_preference") or TradePreference.DIRECT_ONLY.value).upper()
    if user_pref:
        pref = user_pref.upper()
    if pref != TradePreference.CHAIN_ALLOWED.value:
        return False
    return True


def chain_feature_enabled() -> bool:
    return change_chain_enabled()


def matchability_report(row: dict[str, Any], *, user_pref: str | None = None) -> dict[str, Any]:
    mod = _moderation_of(row)
    inv = _inventory_of(row)
    public_ok = is_public_matchable(row)
    chain_ok = is_chain_candidate(row, user_pref=user_pref)
    reasons: list[str] = []
    if mod != ModerationStatus.APPROVED:
        reasons.append("MODERATION_NOT_APPROVED")
    if inv in INVENTORY_BLOCKED or inv != InventoryStatus.AVAILABLE:
        reasons.append(f"INVENTORY_{inv.value}")
    if not bool(int(row.get("chain_opt_in") or 0)):
        reasons.append("CHAIN_OPT_IN_FALSE")
    pref = (row.get("trade_preference") or TradePreference.DIRECT_ONLY.value).upper()
    if user_pref:
        pref = user_pref.upper()
    if pref == TradePreference.DIRECT_ONLY.value:
        reasons.append("DIRECT_ONLY")
    return {
        "listing_id": row.get("id"),
        "moderation_status": mod.value,
        "inventory_status": inv.value,
        "public_matchable": public_ok,
        "chain_candidate": chain_ok,
        "chain_feature_enabled": change_chain_enabled(),
        "reasons": reasons if not chain_ok else [],
        "moderation_version": row.get("moderation_version"),
    }
