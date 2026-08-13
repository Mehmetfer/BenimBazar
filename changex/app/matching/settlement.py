"""Proposal vs settlement boundary — Asset Lock / settlement NOT_IMPLEMENTED.

Chain Engine V1 records multi-party consent only. Calling anything in this
module must never transfer ownership or mutate inventory.
"""

from __future__ import annotations

from typing import Any

from .asset_lock import AssetLockError, guarded_asset_lock_call

# Canonical public markers (do not invent a settled state in V1).
SETTLEMENT_STATUS = "NOT_IMPLEMENTED"
ASSET_LOCK_STATUS = "NOT_IMPLEMENTED"
ENGINE_PHASE_PROPOSAL = "PROPOSAL_ONLY"
ENGINE_PHASE_SETTLEMENT = "SETTLEMENT"  # reserved; never reached in V1


def settlement_capability() -> dict[str, Any]:
    """Machine + human readable settlement capability (always NOT_IMPLEMENTED in V1)."""
    return {
        "engine_phase": ENGINE_PHASE_PROPOSAL,
        "settlement": SETTLEMENT_STATUS,
        "asset_lock": ASSET_LOCK_STATUS,
        "ownership_transferred": False,
        "settlement_available": False,
        "user_message": (
            "Zincir önerisi ve onay (consent) kaydedilir; "
            "Asset Lock / mülkiyet transferi henüz uygulanmadı (NOT_IMPLEMENTED)."
        ),
        "message": "Asset Lock settlement is NOT_IMPLEMENTED in Chain Engine V1",
    }


def feature_disabled_payload() -> dict[str, Any]:
    """User-facing payload when CHANGE_CHAIN_ENABLED is off."""
    return {
        "code": "CHANGE_CHAIN_DISABLED",
        "message": "Change Chain feature flag kapalı",
        "user_message": (
            "Çoklu takas zinciri şu an kapalı. "
            "Doğrudan (iki taraflı) takas kullanabilirsiniz. "
            "Settlement / Asset Lock da henüz yok (NOT_IMPLEMENTED)."
        ),
        "feature_flag": "CHANGE_CHAIN_ENABLED=false",
        "engine_phase": ENGINE_PHASE_PROPOSAL,
        "settlement": SETTLEMENT_STATUS,
        "asset_lock": ASSET_LOCK_STATUS,
        "settlement_available": False,
    }


def attempt_settlement(chain_id: str, listing_ids: list[int]) -> dict[str, Any]:
    """
    Explicit settlement entrypoint — always fails with NOT_IMPLEMENTED.

    Kept so API/UI cannot confuse ACCEPTED (consent) with completed settlement.
    """
    try:
        guarded_asset_lock_call("lock", chain_id, listing_ids)
    except AssetLockError as exc:
        return {
            "code": "NOT_IMPLEMENTED",
            "settlement": SETTLEMENT_STATUS,
            "asset_lock": ASSET_LOCK_STATUS,
            "engine_phase": ENGINE_PHASE_PROPOSAL,
            "ownership_transferred": False,
            "settlement_available": False,
            "chain_id": chain_id,
            "listing_ids": list(listing_ids),
            "message": exc.message,
            "user_message": (
                "Onay tamamlanmış olsa bile mülkiyet transferi yapılmaz. "
                "Asset Lock settlement NOT_IMPLEMENTED."
            ),
            "asset_lock_code": exc.code,
        }
    # Unreachable with NotImplementedAssetLock; defensive.
    return {
        "code": "NOT_IMPLEMENTED",
        "settlement": SETTLEMENT_STATUS,
        "asset_lock": ASSET_LOCK_STATUS,
        "ownership_transferred": False,
    }


def attach_proposal_boundary(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge settlement boundary fields onto proposal/match responses."""
    cap = settlement_capability()
    out = dict(payload)
    out.update(cap)
    return out
