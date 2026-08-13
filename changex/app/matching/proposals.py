"""Chain Proposal persistence + all-party consent (no settlement)."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from .. import db
from ..domain_status import InventoryStatus, ModerationStatus
from .config import CHANGE_CHAIN_PROPOSAL_TTL_SECONDS, CHAIN_ENGINE_VERSION
from .cycles import ChainCycle
from .explain import explain_cycle
from .integrity import GraphIntegrityError, revalidate_stored_edges
from .matchability import is_chain_candidate
from .settlement import attach_proposal_boundary


class ChainProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    ACCEPTED = "ACCEPTED"  # all-party consent recorded — NOT settled
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    # Settlement stubs (not used in Chain Engine V1)
    LOCKING = "LOCKING"
    LOCKED = "LOCKED"
    COMMITTING = "COMMITTING"
    COMPLETED = "COMPLETED"


class ChainConsent(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ChainProposalError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


TERMINAL = {
    ChainProposalStatus.REJECTED,
    ChainProposalStatus.EXPIRED,
    ChainProposalStatus.CANCELLED,
    ChainProposalStatus.COMPLETED,
}


def _now() -> float:
    return time.time()


def persist_proposal(
    conn,
    cycle: ChainCycle,
    *,
    created_by: int,
    nodes_by_id: dict[int, dict[str, Any]],
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    existing = find_open_proposal_for_cycle(conn, cycle.listing_ids)
    if existing is not None:
        return existing

    ttl = ttl_seconds if ttl_seconds is not None else CHANGE_CHAIN_PROPOSAL_TTL_SECONDS
    now = _now()
    chain_id = str(uuid.uuid4())
    explanations = explain_cycle(cycle.edges, nodes_by_id) or list(cycle.explanations)
    edges_payload = [e.to_dict() for e in cycle.edges]
    status = ChainProposalStatus.PROPOSED.value
    cur = conn.execute(
        """
        INSERT INTO chain_proposals(
          chain_id, listing_ids, owner_ids, length, edges_json,
          score, score_breakdowns, explanations, risk_flags,
          status, version, expires_at, created_at, updated_at, created_by, engine_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            chain_id,
            db.dumps(cycle.listing_ids),
            db.dumps(cycle.owner_ids),
            cycle.length,
            db.dumps(edges_payload),
            float(cycle.overall_score),
            db.dumps(cycle.score_breakdowns),
            db.dumps(explanations),
            db.dumps(cycle.risk_flags),
            status,
            1,
            now + int(ttl),
            now,
            now,
            created_by,
            CHAIN_ENGINE_VERSION,
        ),
    )
    proposal_id = int(cur.lastrowid)
    for owner_id, listing_id in zip(cycle.owner_ids, cycle.listing_ids):
        conn.execute(
            """
            INSERT INTO chain_proposal_participants(
              proposal_id, owner_id, listing_id, consent, version, updated_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (proposal_id, int(owner_id), int(listing_id), ChainConsent.PENDING.value, 1, now),
        )
    return proposal_public(conn, proposal_id)


def _canonical_listing_key(listing_ids: list[int]) -> tuple[int, ...]:
    ids = [int(x) for x in listing_ids]
    if not ids:
        return tuple()
    min_i = min(range(len(ids)), key=lambda i: ids[i])
    rotated = ids[min_i:] + ids[:min_i]
    return tuple(rotated)


def find_open_proposal_for_cycle(conn, listing_ids: list[int]) -> dict[str, Any] | None:
    """Reuse non-terminal consent-in-progress proposal for the same cycle."""
    key = _canonical_listing_key(listing_ids)
    if not key:
        return None
    open_statuses = {
        ChainProposalStatus.PROPOSED.value,
        ChainProposalStatus.PARTIALLY_ACCEPTED.value,
    }
    rows = conn.execute(
        """
        SELECT * FROM chain_proposals
        WHERE status IN (?, ?)
        ORDER BY created_at DESC
        """,
        (
            ChainProposalStatus.PROPOSED.value,
            ChainProposalStatus.PARTIALLY_ACCEPTED.value,
        ),
    ).fetchall()
    for row in rows:
        d = dict(row)
        d = _expire_if_needed(conn, d)
        if d["status"] not in open_statuses:
            continue
        if _canonical_listing_key(db.loads(d["listing_ids"], [])) == key:
            return _row_to_public(conn, d)
    return None

def proposal_public(conn, proposal_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM chain_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if not row:
        raise ChainProposalError("PROPOSAL_NOT_FOUND", "Proposal yok", 404)
    return _row_to_public(conn, dict(row))


def proposal_by_chain_id(conn, chain_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM chain_proposals WHERE chain_id = ?", (chain_id,)).fetchone()
    if not row:
        raise ChainProposalError("PROPOSAL_NOT_FOUND", "Proposal yok", 404)
    return _row_to_public(conn, dict(row))


def _row_to_public(conn, row: dict[str, Any]) -> dict[str, Any]:
    parts = conn.execute(
        "SELECT * FROM chain_proposal_participants WHERE proposal_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    participants = [
        {
            "owner_id": int(p["owner_id"]),
            "listing_id": int(p["listing_id"]),
            "consent": p["consent"],
            "version": int(p["version"] or 1),
            "updated_at": p["updated_at"],
        }
        for p in parts
    ]
    return attach_proposal_boundary({
        "id": row["id"],
        "chain_id": row["chain_id"],
        "listing_ids": db.loads(row["listing_ids"], []),
        "owner_ids": db.loads(row["owner_ids"], []),
        "length": int(row["length"]),
        "edges": db.loads(row["edges_json"], []),
        "score": float(row["score"] or 0),
        "score_breakdowns": db.loads(row["score_breakdowns"], []),
        "explanations": db.loads(row["explanations"], []),
        "risk_flags": db.loads(row.get("risk_flags") or "[]", []),
        "status": row["status"],
        "version": int(row["version"] or 1),
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_by": row["created_by"],
        "engine_version": row.get("engine_version") or CHAIN_ENGINE_VERSION,
        "participants": participants,
        "graph_edge_materialized": False,
        "consent_only": True,
    })


def list_proposals_for_user(conn, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT DISTINCT p.*
        FROM chain_proposals p
        JOIN chain_proposal_participants pp ON pp.proposal_id = p.id
        WHERE pp.owner_id = ?
        ORDER BY p.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_public(conn, dict(r)) for r in rows]


def _expire_if_needed(conn, row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] in {s.value for s in TERMINAL}:
        return row
    if float(row["expires_at"] or 0) < _now():
        conn.execute(
            "UPDATE chain_proposals SET status = ?, updated_at = ?, version = version + 1 WHERE id = ?",
            (ChainProposalStatus.EXPIRED.value, _now(), row["id"]),
        )
        row = dict(conn.execute("SELECT * FROM chain_proposals WHERE id = ?", (row["id"],)).fetchone())
    return row


def validate_listings_still_eligible(conn, listing_ids: list[int]) -> None:
    """Re-validate on accept — stale listing / moderation revision invalidates."""
    for lid in listing_ids:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
        if not row:
            raise ChainProposalError("STALE_LISTING", f"Listing {lid} yok", 409)
        d = dict(row)
        mod = str(d.get("moderation_status") or "").upper()
        inv = str(d.get("inventory_status") or "").upper()
        if mod != ModerationStatus.APPROVED.value:
            raise ChainProposalError(
                "MODERATION_INVALID",
                f"Listing {lid} moderation artık APPROVED değil ({mod})",
                409,
            )
        if inv != InventoryStatus.AVAILABLE.value:
            raise ChainProposalError(
                "STALE_LISTING",
                f"Listing {lid} inventory {inv}",
                409,
            )
        if not is_chain_candidate(d):
            raise ChainProposalError(
                "STALE_LISTING",
                f"Listing {lid} artık chain candidate değil",
                409,
            )
        owner = conn.execute("SELECT suspended FROM users WHERE id = ?", (d["owner_id"],)).fetchone()
        if owner and int(owner["suspended"] or 0):
            raise ChainProposalError("STALE_LISTING", "Owner suspended", 409)


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
        (key, user_id, action, entity_type, entity_id, db.dumps(response), _now()),
    )


def accept_proposal(
    conn,
    proposal_id: int,
    *,
    actor_id: int,
    actor_role: str,
    expected_version: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    action = "chain_accept"
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, action)
        if cached is not None:
            return cached

    row = conn.execute("SELECT * FROM chain_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if not row:
        raise ChainProposalError("PROPOSAL_NOT_FOUND", "Proposal yok", 404)
    row = _expire_if_needed(conn, dict(row))
    if row["status"] == ChainProposalStatus.EXPIRED.value:
        raise ChainProposalError("CHAIN_EXPIRED", "Proposal süresi dolmuş", 409)
    if row["status"] in {s.value for s in TERMINAL} and row["status"] != ChainProposalStatus.ACCEPTED.value:
        raise ChainProposalError("CHAIN_TERMINAL", f"Proposal {row['status']}", 409)

    # Admin/Superadmin cannot consent on behalf of users
    if actor_role in {"admin", "superadmin"}:
        # Still may act only if they are a participant owner
        pass

    part = conn.execute(
        "SELECT * FROM chain_proposal_participants WHERE proposal_id = ? AND owner_id = ?",
        (proposal_id, actor_id),
    ).fetchone()
    if not part:
        raise ChainProposalError("FORBIDDEN", "Zincir katılımcısı değilsiniz", 403)

    if expected_version is not None and int(row["version"]) != int(expected_version):
        raise ChainProposalError("CONFLICT", "Proposal version çakışması", 409)

    listing_ids = db.loads(row["listing_ids"], [])
    validate_listings_still_eligible(conn, listing_ids)
    try:
        revalidate_stored_edges(conn, db.loads(row["edges_json"], []))
    except GraphIntegrityError as exc:
        raise ChainProposalError(
            "STALE_EDGE",
            exc.message,
            409,
        ) from exc

    # Idempotent consent: already accepted by this participant
    if part["consent"] == ChainConsent.ACCEPTED.value:
        result = proposal_public(conn, proposal_id)
        if idempotency_key:
            _idempotent_put(conn, idempotency_key, actor_id, action, "chain_proposal", proposal_id, result)
        return result

    if part["consent"] == ChainConsent.REJECTED.value:
        raise ChainProposalError("ALREADY_REJECTED", "Bu katılımcı reddetmiş", 409)

    now = _now()
    # Optimistic lock on proposal version
    cur = conn.execute(
        """
        UPDATE chain_proposals
        SET version = version + 1, updated_at = ?
        WHERE id = ? AND version = ?
        """,
        (now, proposal_id, int(row["version"])),
    )
    if cur.rowcount != 1:
        raise ChainProposalError("CONFLICT", "Eşzamanlı consent çakışması", 409)

    conn.execute(
        """
        UPDATE chain_proposal_participants
        SET consent = ?, version = version + 1, updated_at = ?
        WHERE id = ?
        """,
        (ChainConsent.ACCEPTED.value, now, part["id"]),
    )

    consents = conn.execute(
        "SELECT consent FROM chain_proposal_participants WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchall()
    values = [c["consent"] for c in consents]
    if any(v == ChainConsent.REJECTED.value for v in values):
        new_status = ChainProposalStatus.REJECTED.value
    elif all(v == ChainConsent.ACCEPTED.value for v in values):
        new_status = ChainProposalStatus.ACCEPTED.value
    elif any(v == ChainConsent.ACCEPTED.value for v in values):
        new_status = ChainProposalStatus.PARTIALLY_ACCEPTED.value
    else:
        new_status = ChainProposalStatus.PROPOSED.value

    conn.execute(
        "UPDATE chain_proposals SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, proposal_id),
    )
    # CRITICAL: do NOT transfer ownership / call AssetLock / settle
    result = proposal_public(conn, proposal_id)
    assert result["ownership_transferred"] is False
    assert result["settlement"] == "NOT_IMPLEMENTED"
    assert result["engine_phase"] == "PROPOSAL_ONLY"
    assert result.get("consent_only") is True
    if idempotency_key:
        _idempotent_put(conn, idempotency_key, actor_id, action, "chain_proposal", proposal_id, result)
    return result


def reject_proposal(
    conn,
    proposal_id: int,
    *,
    actor_id: int,
    actor_role: str,
    expected_version: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    action = "chain_reject"
    if idempotency_key:
        cached = _idempotent_get(conn, idempotency_key, actor_id, action)
        if cached is not None:
            return cached

    row = conn.execute("SELECT * FROM chain_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if not row:
        raise ChainProposalError("PROPOSAL_NOT_FOUND", "Proposal yok", 404)
    row = _expire_if_needed(conn, dict(row))
    if row["status"] == ChainProposalStatus.EXPIRED.value:
        raise ChainProposalError("CHAIN_EXPIRED", "Proposal süresi dolmuş", 409)
    if row["status"] in {s.value for s in TERMINAL}:
        # Already rejected — idempotent style return if participant already rejected
        part = conn.execute(
            "SELECT * FROM chain_proposal_participants WHERE proposal_id = ? AND owner_id = ?",
            (proposal_id, actor_id),
        ).fetchone()
        if part and part["consent"] == ChainConsent.REJECTED.value and row["status"] == ChainProposalStatus.REJECTED.value:
            result = proposal_public(conn, proposal_id)
            if idempotency_key:
                _idempotent_put(conn, idempotency_key, actor_id, action, "chain_proposal", proposal_id, result)
            return result
        raise ChainProposalError("CHAIN_TERMINAL", f"Proposal {row['status']}", 409)

    part = conn.execute(
        "SELECT * FROM chain_proposal_participants WHERE proposal_id = ? AND owner_id = ?",
        (proposal_id, actor_id),
    ).fetchone()
    if not part:
        raise ChainProposalError("FORBIDDEN", "Zincir katılımcısı değilsiniz", 403)

    if expected_version is not None and int(row["version"]) != int(expected_version):
        raise ChainProposalError("CONFLICT", "Proposal version çakışması", 409)

    now = _now()
    cur = conn.execute(
        """
        UPDATE chain_proposals
        SET version = version + 1, updated_at = ?, status = ?
        WHERE id = ? AND version = ?
        """,
        (now, ChainProposalStatus.REJECTED.value, proposal_id, int(row["version"])),
    )
    if cur.rowcount != 1:
        raise ChainProposalError("CONFLICT", "Eşzamanlı consent çakışması", 409)

    conn.execute(
        """
        UPDATE chain_proposal_participants
        SET consent = ?, version = version + 1, updated_at = ?
        WHERE id = ?
        """,
        (ChainConsent.REJECTED.value, now, part["id"]),
    )
    result = proposal_public(conn, proposal_id)
    if idempotency_key:
        _idempotent_put(conn, idempotency_key, actor_id, action, "chain_proposal", proposal_id, result)
    return result
