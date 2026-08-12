"""CHANGE X trade engine — atomic, idempotent, race-safe A<->B trades."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from . import db
from .states import (
    ListingStatus,
    TradeState,
    InvalidTransition,
    OFFERABLE_LISTING,
    RELEASE_TO_APPROVED,
    normalize_listing_status,
    transition,
)
from .value import ChangeValue, ChangeValueError, value_gap


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class _IdempotentReplay(Exception):
    """Internal: duplicate idempotency key under concurrency — replay after rollback."""

    def __init__(self, key: str):
        self.key = key


def _listing_units(row: dict[str, Any]) -> int:
    if "mandal_units" in row and row["mandal_units"] is not None:
        return int(row["mandal_units"])
    return int(row.get("value_mandal") or 0)


def _sum_listings(conn, listing_ids: list[int]) -> tuple[ChangeValue, list[dict]]:
    if not listing_ids:
        raise DomainError("EMPTY_LISTINGS", "En az bir listing gerekli")
    if len(set(listing_ids)) != len(listing_ids):
        raise DomainError("DUPLICATE_LISTING", "Aynı listing birden fazla eklenemez")
    rows = []
    total = ChangeValue.zero()
    for lid in listing_ids:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
        if not row:
            raise DomainError("LISTING_NOT_FOUND", f"Listing {lid} bulunamadı", 404)
        d = dict(row)
        status = normalize_listing_status(d["status"])
        if status not in OFFERABLE_LISTING:
            raise DomainError(
                "LISTING_NOT_APPROVED",
                f"İlan #{lid} onaylı değil ({status.value}). "
                "Teklif için yalnızca onaylanmış ilanlar kullanılabilir.",
                409,
            )
        units = _listing_units(d)
        total = total.add(ChangeValue.from_mandal_units(units))
        rows.append(d)
    return total, rows


def create_offer(
    conn,
    *,
    proposer_id: int,
    requested_listing_ids: list[int],
    offered_listing_ids: list[int],
    idempotency_key: str | None = None,
    expires_in_seconds: int = 86_400,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    correlation_id = correlation_id or str(uuid.uuid4())
    try:
        with db.immediate_tx(conn):
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM trades WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if existing:
                    return trade_public(conn, dict(existing))

            req_value, req_rows = _sum_listings(conn, requested_listing_ids)
            off_value, off_rows = _sum_listings(conn, offered_listing_ids)

            # Ownership: offered must belong to proposer; requested must NOT.
            for r in off_rows:
                if int(r["owner_id"]) != proposer_id:
                    raise DomainError("NOT_OWNER", "Teklif ettiğin listing sana ait değil", 403)
            receivers = {int(r["owner_id"]) for r in req_rows}
            if len(receivers) != 1:
                raise DomainError("MULTI_RECEIVER", "İstenen listingler tek alıcıya ait olmalı")
            receiver_id = next(iter(receivers))
            if receiver_id == proposer_id:
                raise DomainError("SELF_TRADE", "Kendi kaydına teklif veremezsin")
            for r in req_rows:
                if int(r["owner_id"]) == proposer_id:
                    raise DomainError("SELF_TRADE", "Kendi kaydını isteyemezsin")

            overlap = set(requested_listing_ids) & set(offered_listing_ids)
            if overlap:
                raise DomainError("OVERLAP", "Aynı listing her iki tarafta olamaz")

            gap = req_value.mandal_units - off_value.mandal_units
            now = time.time()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO trades(
                      proposer_id, receiver_id, offered_listing_ids, requested_listing_ids,
                      calculated_offered_mandal_units, calculated_requested_mandal_units,
                      value_gap_mandal_units, status, version, idempotency_key,
                      created_at, updated_at, expires_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        proposer_id,
                        receiver_id,
                        db.dumps(offered_listing_ids),
                        db.dumps(requested_listing_ids),
                        off_value.mandal_units,
                        req_value.mandal_units,
                        gap,
                        TradeState.OFFERED.value,
                        1,
                        idempotency_key,
                        now,
                        now,
                        now + expires_in_seconds,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if idempotency_key:
                    raise _IdempotentReplay(idempotency_key) from exc
                raise
            trade_id = int(cur.lastrowid)
            _event(
                conn,
                trade_id,
                proposer_id,
                None,
                TradeState.OFFERED,
                "Teklif oluşturuldu",
                correlation_id,
            )
            db.audit(
                conn,
                actor_id=proposer_id,
                action="offer.create",
                entity="trade",
                entity_id=trade_id,
                detail=f"offered={offered_listing_ids} requested={requested_listing_ids}",
                correlation_id=correlation_id,
            )
            if idempotency_key:
                result_preview = trade_public(
                    conn,
                    dict(
                        conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
                    ),
                )
                _idempotent_put(
                    conn, idempotency_key, proposer_id, "offer", "trade", trade_id, result_preview
                )
            row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
            return trade_public(conn, dict(row))
    except _IdempotentReplay as replay:
        existing = conn.execute(
            "SELECT * FROM trades WHERE idempotency_key = ?", (replay.key,)
        ).fetchone()
        if existing:
            return trade_public(conn, dict(existing))
        raise DomainError("IDEMPOTENCY_CONFLICT", "Tekrarlayan teklif çakışması", 409) from replay


def accept_offer(
    conn,
    *,
    trade_id: int,
    actor_id: int,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Accept offer: reserve all involved listings atomically. Race-safe."""
    correlation_id = correlation_id or str(uuid.uuid4())
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, "accept")
        if cached is not None:
            return cached

    with db.immediate_tx(conn):
        trade = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if not trade:
            raise DomainError("TRADE_NOT_FOUND", "Takas bulunamadı", 404)
        t = dict(trade)
        if int(t["receiver_id"]) != actor_id:
            raise DomainError("FORBIDDEN", "Sadece alıcı kabul edebilir", 403)

        # Idempotent accept if already accepted+ by same flow
        current = TradeState(t["status"] if t.get("status") else t.get("state"))
        if current in {
            TradeState.ACCEPTED,
            TradeState.CONFIRMED,
            TradeState.IN_TRANSFER,
            TradeState.DELIVERED,
            TradeState.COMPLETED,
        }:
            result = trade_public(conn, t)
            if idempotency_key:
                _idempotent_put(conn, idempotency_key, actor_id, "accept", "trade", trade_id, result)
            return result

        if t.get("expires_at") and float(t["expires_at"]) < time.time():
            _force_status(conn, t, TradeState.EXPIRED, actor_id, "Süresi doldu", correlation_id)
            raise DomainError("OFFER_EXPIRED", "Teklif süresi dolmuş", 409)

        try:
            transition(current, TradeState.ACCEPTED)
        except InvalidTransition as exc:
            raise DomainError("INVALID_STATE", str(exc), 400) from exc

        offered = db.loads(t["offered_listing_ids"], [])
        requested = db.loads(t["requested_listing_ids"], [])
        all_ids = list(offered) + list(requested)

        # Reserve each listing with optimistic version check
        for idx, lid in enumerate(all_ids):
            row = conn.execute(
                "SELECT id, status, version FROM trade_listings WHERE id = ?",
                (lid,),
            ).fetchone()
            if not row:
                raise DomainError("LISTING_NOT_FOUND", f"Listing {lid} yok", 404)
            if normalize_listing_status(row["status"]) not in OFFERABLE_LISTING:
                raise DomainError(
                    "CONFLICT",
                    f"Listing {lid} müsait değil ({row['status']})",
                    409,
                )
            cur = conn.execute(
                """
                UPDATE trade_listings
                SET status = ?, version = version + 1, updated_at = ?
                WHERE id = ? AND status IN ('APPROVED', 'ACTIVE') AND version = ?
                """,
                (
                    ListingStatus.RESERVED.value,
                    time.time(),
                    lid,
                    row["version"],
                ),
            )
            if cur.rowcount != 1:
                raise DomainError("CONFLICT", f"Listing {lid} için yarış çakışması", 409)
            db.sync_dual_status(
                conn,
                int(lid),
                moderation_status="APPROVED",
                inventory_status="RESERVED",
                legacy_status=ListingStatus.RESERVED.value,
            )
            db.audit(
                conn,
                actor_id=actor_id,
                action="listing.reserve",
                entity="listing",
                entity_id=lid,
                correlation_id=correlation_id,
            )
            # Test hook: fail after first listing reserved to prove full rollback
            db.maybe_fail(f"after_reserve_{idx}")

        now = time.time()
        cur = conn.execute(
            """
            UPDATE trades
            SET status = ?, accepted_at = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND status = ? AND version = ?
            """,
            (
                TradeState.ACCEPTED.value,
                now,
                now,
                trade_id,
                current.value,
                t["version"],
            ),
        )
        if cur.rowcount != 1:
            raise DomainError("CONFLICT", "Teklif kabul yarışı kaybedildi", 409)

        _event(conn, trade_id, actor_id, current, TradeState.ACCEPTED, "Kabul edildi", correlation_id)
        db.audit(
            conn,
            actor_id=actor_id,
            action="offer.accept",
            entity="trade",
            entity_id=trade_id,
            correlation_id=correlation_id,
        )
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        result = trade_public(conn, dict(row))
        if idempotency_key:
            _idempotent_put(conn, idempotency_key, actor_id, "accept", "trade", trade_id, result)
        return result


def complete_trade(
    conn,
    *,
    trade_id: int,
    actor_id: int,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Atomically swap listing ownership and mark TRADED + COMPLETED."""
    correlation_id = correlation_id or str(uuid.uuid4())
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, "complete")
        if cached is not None:
            return cached

    with db.immediate_tx(conn):
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise DomainError("TRADE_NOT_FOUND", "Takas bulunamadı", 404)
        t = dict(trade)
        if actor_id not in (int(t["proposer_id"]), int(t["receiver_id"])):
            # allow admin via caller
            user = conn.execute("SELECT role FROM users WHERE id = ?", (actor_id,)).fetchone()
            if not user or user["role"] != "admin":
                raise DomainError("FORBIDDEN", "Bu takasa erişimin yok", 403)

        current = TradeState(t["status"] if t.get("status") else t.get("state"))
        if current == TradeState.COMPLETED:
            result = trade_public(conn, t)
            if idempotency_key:
                _idempotent_put(conn, idempotency_key, actor_id, "complete", "trade", trade_id, result)
            return result

        # Allow shortcut COMPLETED from ACCEPTED/CONFIRMED/IN_TRANSFER/DELIVERED via chain
        path = _path_to_completed(current)
        if path is None:
            raise DomainError("INVALID_STATE", f"{current.value} tamamlanamaz", 400)

        offered = [int(x) for x in db.loads(t["offered_listing_ids"], [])]
        requested = [int(x) for x in db.loads(t["requested_listing_ids"], [])]
        proposer_id = int(t["proposer_id"])
        receiver_id = int(t["receiver_id"])

        # Transfer: offered -> receiver, requested -> proposer
        for lid in offered:
            _transfer_listing(conn, lid, new_owner=receiver_id, correlation_id=correlation_id)
        for lid in requested:
            _transfer_listing(conn, lid, new_owner=proposer_id, correlation_id=correlation_id)

        now = time.time()
        from_state = current
        for step in path:
            _event(conn, trade_id, actor_id, from_state, step, "atomic complete", correlation_id)
            from_state = step

        cur = conn.execute(
            """
            UPDATE trades
            SET status = ?, completed_at = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND version = ?
            """,
            (TradeState.COMPLETED.value, now, now, trade_id, t["version"]),
        )
        if cur.rowcount != 1:
            raise DomainError("CONFLICT", "Tamamlama yarışı", 409)

        db.audit(
            conn,
            actor_id=actor_id,
            action="trade.completion",
            entity="trade",
            entity_id=trade_id,
            correlation_id=correlation_id,
        )
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        result = trade_public(conn, dict(row))
        if idempotency_key:
            _idempotent_put(conn, idempotency_key, actor_id, "complete", "trade", trade_id, result)
        return result


def cancel_offer(
    conn,
    *,
    trade_id: int,
    actor_id: int,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    correlation_id = correlation_id or str(uuid.uuid4())
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, "cancel")
        if cached is not None:
            return cached

    with db.immediate_tx(conn):
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise DomainError("TRADE_NOT_FOUND", "Takas bulunamadı", 404)
        t = dict(trade)
        if actor_id not in (int(t["proposer_id"]), int(t["receiver_id"])):
            raise DomainError("FORBIDDEN", "Bu teklifi iptal edemezsin", 403)
        current = TradeState(t["status"] if t.get("status") else t.get("state"))
        if current == TradeState.CANCELLED:
            result = trade_public(conn, t)
            if idempotency_key:
                _idempotent_put(conn, idempotency_key, actor_id, "cancel", "trade", trade_id, result)
            return result
        try:
            transition(current, TradeState.CANCELLED)
        except InvalidTransition as exc:
            raise DomainError("INVALID_STATE", str(exc), 400) from exc

        # Release reserved listings if any
        if current in {TradeState.ACCEPTED, TradeState.CONFIRMED, TradeState.IN_TRANSFER}:
            for lid in db.loads(t["offered_listing_ids"], []) + db.loads(
                t["requested_listing_ids"], []
            ):
                conn.execute(
                    """
                    UPDATE trade_listings
                    SET status = ?, version = version + 1, updated_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        RELEASE_TO_APPROVED.value,
                        time.time(),
                        int(lid),
                        ListingStatus.RESERVED.value,
                    ),
                )
                db.sync_dual_status(
                    conn,
                    int(lid),
                    moderation_status="APPROVED",
                    inventory_status="AVAILABLE",
                    legacy_status=RELEASE_TO_APPROVED.value,
                )
                db.audit(
                    conn,
                    actor_id=actor_id,
                    action="listing.release",
                    entity="listing",
                    entity_id=int(lid),
                    correlation_id=correlation_id,
                )

        now = time.time()
        conn.execute(
            """
            UPDATE trades
            SET status = ?, cancelled_at = ?, updated_at = ?, version = version + 1
            WHERE id = ?
            """,
            (TradeState.CANCELLED.value, now, now, trade_id),
        )
        _event(conn, trade_id, actor_id, current, TradeState.CANCELLED, "İptal", correlation_id)
        db.audit(
            conn,
            actor_id=actor_id,
            action="offer.cancel",
            entity="trade",
            entity_id=trade_id,
            correlation_id=correlation_id,
        )
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        result = trade_public(conn, dict(row))
        if idempotency_key:
            _idempotent_put(conn, idempotency_key, actor_id, "cancel", "trade", trade_id, result)
        return result


def confirm_trade(
    conn,
    *,
    trade_id: int,
    actor_id: int,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return _simple_transition(
        conn,
        trade_id=trade_id,
        actor_id=actor_id,
        target=TradeState.CONFIRMED,
        action="trade.confirmation",
        idempotency_key=idempotency_key,
        idem_action="confirm",
        correlation_id=correlation_id,
    )


def _simple_transition(
    conn,
    *,
    trade_id: int,
    actor_id: int,
    target: TradeState,
    action: str,
    idempotency_key: str | None,
    idem_action: str,
    correlation_id: str | None,
) -> dict[str, Any]:
    correlation_id = correlation_id or str(uuid.uuid4())
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, idem_action)
        if cached is not None:
            return cached

    with db.immediate_tx(conn):
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise DomainError("TRADE_NOT_FOUND", "Takas bulunamadı", 404)
        t = dict(trade)
        if actor_id not in (int(t["proposer_id"]), int(t["receiver_id"])):
            raise DomainError("FORBIDDEN", "Bu takasa erişimin yok", 403)
        current = TradeState(t["status"] if t.get("status") else t.get("state"))
        if current == target:
            result = trade_public(conn, t)
            if idempotency_key:
                _idempotent_put(conn, idempotency_key, actor_id, idem_action, "trade", trade_id, result)
            return result
        try:
            transition(current, target)
        except InvalidTransition as exc:
            raise DomainError("INVALID_STATE", str(exc), 400) from exc
        now = time.time()
        cur = conn.execute(
            """
            UPDATE trades SET status = ?, updated_at = ?, version = version + 1
            WHERE id = ? AND version = ?
            """,
            (target.value, now, trade_id, t["version"]),
        )
        if cur.rowcount != 1:
            raise DomainError("CONFLICT", "State yarışı", 409)
        _event(conn, trade_id, actor_id, current, target, action, correlation_id)
        db.audit(
            conn,
            actor_id=actor_id,
            action=action,
            entity="trade",
            entity_id=trade_id,
            correlation_id=correlation_id,
        )
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        result = trade_public(conn, dict(row))
        if idempotency_key:
            _idempotent_put(conn, idempotency_key, actor_id, idem_action, "trade", trade_id, result)
        return result


def _transfer_listing(conn, listing_id: int, *, new_owner: int, correlation_id: str) -> None:
    row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    if not row:
        raise DomainError("LISTING_NOT_FOUND", f"Listing {listing_id} yok", 404)
    status = str(row["status"]).upper()
    if status not in {ListingStatus.RESERVED.value, ListingStatus.APPROVED.value, ListingStatus.ACTIVE.value}:
        raise DomainError("CONFLICT", f"Listing {listing_id} transfer edilemez", 409)
    cur = conn.execute(
        """
        UPDATE trade_listings
        SET owner_id = ?, status = ?, version = version + 1, updated_at = ?
        WHERE id = ? AND version = ?
        """,
        (new_owner, ListingStatus.TRADED.value, time.time(), listing_id, row["version"]),
    )
    if cur.rowcount != 1:
        raise DomainError("CONFLICT", f"Listing {listing_id} transfer çakışması", 409)
    db.sync_dual_status(
        conn,
        listing_id,
        moderation_status="APPROVED",
        inventory_status="TRADED",
        legacy_status=ListingStatus.TRADED.value,
    )
    db.audit(
        conn,
        actor_id=new_owner,
        action="listing.traded",
        entity="listing",
        entity_id=listing_id,
        correlation_id=correlation_id,
    )


def _path_to_completed(current: TradeState) -> list[TradeState] | None:
    """Return intermediate states including COMPLETED, or None if impossible."""
    if current == TradeState.COMPLETED:
        return []
    # Explicit allowed shortcuts for atomic completion in V1
    sequences = {
        TradeState.ACCEPTED: [
            TradeState.CONFIRMED,
            TradeState.IN_TRANSFER,
            TradeState.DELIVERED,
            TradeState.COMPLETED,
        ],
        TradeState.CONFIRMED: [
            TradeState.IN_TRANSFER,
            TradeState.DELIVERED,
            TradeState.COMPLETED,
        ],
        TradeState.IN_TRANSFER: [TradeState.DELIVERED, TradeState.COMPLETED],
        TradeState.DELIVERED: [TradeState.COMPLETED],
    }
    return sequences.get(current)


def _force_status(conn, trade: dict, target: TradeState, actor_id: int, note: str, cid: str) -> None:
    current = TradeState(trade["status"] if trade.get("status") else trade.get("state"))
    conn.execute(
        "UPDATE trades SET status = ?, updated_at = ?, version = version + 1 WHERE id = ?",
        (target.value, time.time(), trade["id"]),
    )
    _event(conn, int(trade["id"]), actor_id, current, target, note, cid)


def _event(conn, trade_id, actor_id, from_state, to_state, note, correlation_id) -> None:
    conn.execute(
        """
        INSERT INTO trade_events(trade_id, actor_id, from_state, to_state, note, correlation_id, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            trade_id,
            actor_id,
            from_state.value if isinstance(from_state, TradeState) else from_state,
            to_state.value if isinstance(to_state, TradeState) else to_state,
            note,
            correlation_id,
            time.time(),
        ),
    )


def _idempotent_get(conn, key: str, user_id: int, action: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM idempotency_keys WHERE key = ? AND user_id = ? AND action = ?",
        (key, user_id, action),
    ).fetchone()
    if not row:
        return None
    return db.loads(row["response_json"], {})


def _idempotent_put(conn, key, user_id, action, entity_type, entity_id, response) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO idempotency_keys(key, user_id, action, entity_type, entity_id, response_json, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (key, user_id, action, entity_type, entity_id, db.dumps(response), time.time()),
    )


def trade_public(conn, row: dict[str, Any]) -> dict[str, Any]:
    offered_ids = db.loads(row.get("offered_listing_ids"), [])
    requested_ids = db.loads(row.get("requested_listing_ids"), [])
    offered = ChangeValue.from_mandal_units(int(row.get("calculated_offered_mandal_units") or 0))
    requested = ChangeValue.from_mandal_units(
        int(row.get("calculated_requested_mandal_units") or 0)
    )
    gap = value_gap(requested, offered)
    status = row.get("status") or row.get("state")
    return {
        "id": row["id"],
        "proposer_id": row.get("proposer_id") or row.get("initiator_id"),
        "receiver_id": row.get("receiver_id") or row.get("counterparty_id"),
        "offered_listing_ids": offered_ids,
        "requested_listing_ids": requested_ids,
        "calculated_value": {
            "offered": offered.serialize(),
            "requested": requested.serialize(),
        },
        "value_gap": gap["value_gap"],
        "value_gap_mandal_units": gap["value_gap_mandal_units"],
        "value_gap_display": gap["value_gap_display"],
        "exact_match": gap["exact_match"],
        "status": status,
        "state": status,  # back-compat for Flutter
        "version": row.get("version", 1),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "expires_at": row.get("expires_at"),
        "accepted_at": row.get("accepted_at"),
        "cancelled_at": row.get("cancelled_at"),
        "completed_at": row.get("completed_at"),
        "match": gap,  # back-compat
        "settlement_note": gap["settlement"],
    }
