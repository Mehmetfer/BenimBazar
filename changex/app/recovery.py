"""Recovery helpers for interrupted transactions / stale locks."""

from __future__ import annotations

import time
from typing import Any

from . import db
from .states import ListingStatus, TradeState


STALE_RESERVED_SECONDS = 15 * 60  # 15 minutes


def recover_stale_reservations(
    conn,
    *,
    older_than_seconds: int = STALE_RESERVED_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Release RESERVED listings whose trade is cancelled/expired/stuck.

    Safe for process-crash leftovers: if a listing is RESERVED but no
    ACCEPTED/CONFIRMED/IN_TRANSFER/DELIVERED trade references it, release it.
    """
    now = now or time.time()
    active_lock_states = {
        TradeState.ACCEPTED.value,
        TradeState.CONFIRMED.value,
        TradeState.IN_TRANSFER.value,
        TradeState.DELIVERED.value,
    }
    reserved = conn.execute(
        "SELECT * FROM trade_listings WHERE status = ?",
        (ListingStatus.RESERVED.value,),
    ).fetchall()
    released = 0
    for row in reserved:
        lid = int(row["id"])
        updated = float(row["updated_at"] or row["created_at"] or 0)
        if now - updated < older_than_seconds:
            continue
        # Is any locking trade still referencing this listing?
        trades = conn.execute(
            "SELECT id, status, offered_listing_ids, requested_listing_ids FROM trades"
        ).fetchall()
        locked = False
        for t in trades:
            if str(t["status"]) not in active_lock_states:
                continue
            offered = db.loads(t["offered_listing_ids"], [])
            requested = db.loads(t["requested_listing_ids"], [])
            if lid in offered or lid in requested:
                locked = True
                break
        if locked:
            continue
        conn.execute(
            """
            UPDATE trade_listings
            SET status = ?, version = version + 1, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (ListingStatus.APPROVED.value, now, lid, ListingStatus.RESERVED.value),
        )
        db.audit(
            conn,
            actor_id=None,
            action="listing.release_stale",
            entity="listing",
            entity_id=lid,
            detail="recovery",
        )
        released += 1
    return {"released": released, "scanned": len(reserved)}
