"""Listing moderation pipeline — AI is decision support only; Superadmin publishes."""

from __future__ import annotations

import time
import uuid
from typing import Any

from .. import db
from ..states import (
    POLICY_VERSION,
    AiModerationResult,
    ListingStatus,
    MODERATION_STAFF_ROLES,
    ModerationDecision,
    RiskLevel,
    UserRole,
    InvalidTransition,
    listing_transition,
    normalize_listing_status,
)
from .provider import ModerationAssessment, get_provider, validate_assessment
from .cache import invalidate_listing, invalidate_public_listings


class ModerationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _priority_for(ai: ModerationAssessment) -> int:
    # Higher = more urgent in queue
    if ai.result == AiModerationResult.BLOCKED or ai.risk_level == RiskLevel.CRITICAL:
        return 100
    if ai.result == AiModerationResult.HIGH_RISK or ai.risk_level == RiskLevel.HIGH:
        return 80
    if ai.result == AiModerationResult.REVIEW or ai.risk_level == RiskLevel.MEDIUM:
        return 50
    if ai.result == AiModerationResult.UNAVAILABLE:
        return 70
    return 10  # SAFE still queues for Superadmin


def run_ai_premoderation(
    conn,
    *,
    listing_id: int,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Run AI on listing content; never APPROVES. Fail-safe → MODERATION_UNAVAILABLE."""
    correlation_id = correlation_id or str(uuid.uuid4())
    row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    if not row:
        raise ModerationError("LISTING_NOT_FOUND", "Listing yok", 404)
    listing = dict(row)
    current = normalize_listing_status(listing["status"])
    # Move through AI_REVIEW when coming from PENDING
    if current == ListingStatus.PENDING_MODERATION:
        listing_transition(current, ListingStatus.AI_REVIEW)
        conn.execute(
            "UPDATE trade_listings SET status = ?, updated_at = ? WHERE id = ?",
            (ListingStatus.AI_REVIEW.value, time.time(), listing_id),
        )
        current = ListingStatus.AI_REVIEW

    photos = db.loads(listing.get("photo_urls"), [])
    provider = get_provider()
    try:
        raw = provider.analyze_listing(
            title=listing.get("title") or "",
            description=listing.get("description") or "",
            category=listing.get("category") or "",
            wanted_items=listing.get("wanted_items") or "",
            photo_urls=photos,
        )
        assessment = validate_assessment(raw)
    except Exception as exc:  # noqa: BLE001 — fail closed (timeout/unavailable/etc.)
        assessment = ModerationAssessment(
            result=AiModerationResult.UNAVAILABLE,
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            categories=["PROVIDER_ERROR"],
            findings=[],
            error=str(exc)[:200],
        )

    now = time.time()
    if assessment.result == AiModerationResult.UNAVAILABLE or assessment.confidence is None:
        next_status = ListingStatus.MODERATION_UNAVAILABLE
        # Prefer ADMIN_REVIEW synonym path when policy wants queue visibility
        listing_transition(current, next_status)
        risk = RiskLevel.HIGH.value
        priority = 70
    elif assessment.result == AiModerationResult.BLOCKED and (
        "CHILD_SAFETY" in assessment.categories
        or "CSAM" in assessment.categories
        or "HUMAN_TRAFFICKING" in assessment.categories
    ):
        # Hard safety: reject + escalate record; still auditable
        next_status = ListingStatus.REJECTED
        listing_transition(current, next_status)
        risk = RiskLevel.CRITICAL.value
        priority = 100
    else:
        next_status = ListingStatus.ADMIN_REVIEW
        listing_transition(current, next_status)
        risk = assessment.risk_level.value
        priority = _priority_for(assessment)

    mod_version = int(listing.get("moderation_version") or 1)
    conn.execute(
        """
        UPDATE trade_listings SET
          status = ?,
          ai_result = ?,
          ai_confidence = ?,
          ai_categories = ?,
          ai_policy_version = ?,
          risk_level = ?,
          moderation_priority = ?,
          moderation_updated_at = ?,
          updated_at = ?
        WHERE id = ?
        """,
        (
            next_status.value,
            assessment.result.value,
            float(assessment.confidence),
            db.dumps(assessment.categories),
            assessment.policy_version or POLICY_VERSION,
            risk,
            priority,
            now,
            now,
            listing_id,
        ),
    )

    # Photo-level rows
    for url in photos:
        img_flag = "PENDING"
        for ir in assessment.image_results:
            if isinstance(ir, dict) and ir.get("url") == url:
                img_flag = "FLAGGED" if ir.get("flagged") else "AI_SAFE"
        conn.execute(
            """
            INSERT INTO listing_photos(listing_id, url, moderation_status, moderation_version, created_at)
            VALUES (?,?,?,?,?)
            """,
            (listing_id, url, img_flag, mod_version, now),
        )

    conn.execute(
        """
        INSERT INTO moderation_reviews(
          listing_id, moderation_version, ai_result, ai_confidence, ai_payload,
          risk_level, priority, status, policy_version, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            listing_id,
            mod_version,
            assessment.result.value,
            float(assessment.confidence),
            db.dumps(assessment.to_dict()),
            risk,
            priority,
            next_status.value,
            assessment.policy_version or POLICY_VERSION,
            now,
            now,
        ),
    )

    # Bump user risk on severe AI signals
    if assessment.result in {AiModerationResult.HIGH_RISK, AiModerationResult.BLOCKED}:
        bump = 15 if assessment.result == AiModerationResult.BLOCKED else 8
        conn.execute(
            "UPDATE users SET user_risk_score = COALESCE(user_risk_score, 0) + ? WHERE id = ?",
            (bump, listing["owner_id"]),
        )

    db.audit(
        conn,
        actor_id=None,
        action="moderation.ai_precheck",
        entity="listing",
        entity_id=listing_id,
        detail=db.dumps(
            {
                "ai_result": assessment.result.value,
                "confidence": assessment.confidence,
                "next_status": next_status.value,
                "policy_version": assessment.policy_version,
            }
        ),
        correlation_id=correlation_id,
    )
    invalidate_listing(listing_id)
    db.sync_dual_status(conn, listing_id, legacy_status=next_status.value)
    return {
        "listing_id": listing_id,
        "status": next_status.value,
        "ai": assessment.to_dict(),
        "priority": priority,
    }


def apply_moderation_decision(
    conn,
    *,
    listing_id: int,
    actor_id: int,
    actor_role: str,
    decision: ModerationDecision,
    reason: str = "",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Staff moderation decision — admin / moderator / superadmin.

    Superadmin: all decisions including SUSPEND_USER.
    Admin/Moderator: APPROVE, REJECT, REQUEST_EDIT, DELETE (soft), ESCALATE.
    """
    if actor_role not in MODERATION_STAFF_ROLES:
        raise ModerationError("STAFF_REQUIRED", "Moderasyon yetkisi gerekli", 403)

    # Only Superadmin may suspend users via moderation decision
    if decision == ModerationDecision.SUSPEND_USER and actor_role != UserRole.SUPERADMIN.value:
        raise ModerationError(
            "SUPERADMIN_REQUIRED",
            "Kullanıcı askıya alma yalnızca Superadmin",
            403,
        )

    correlation_id = correlation_id or str(uuid.uuid4())

    row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    if not row:
        raise ModerationError("LISTING_NOT_FOUND", "Listing yok", 404)
    listing = dict(row)
    previous = normalize_listing_status(listing["status"])
    version = int(listing.get("version") or 1)
    mod_version = int(listing.get("moderation_version") or 1)

    target_map = {
        ModerationDecision.APPROVE: ListingStatus.APPROVED,
        ModerationDecision.REJECT: ListingStatus.REJECTED,
        ModerationDecision.REQUEST_EDIT: ListingStatus.EDIT_REQUIRED,
        ModerationDecision.ESCALATE: ListingStatus.ESCALATED,
        ModerationDecision.SUSPEND_USER: ListingStatus.SUSPENDED,
        ModerationDecision.DELETE: ListingStatus.CANCELLED,
    }
    target = target_map[decision]

    if decision == ModerationDecision.APPROVE:
        if previous not in {
            ListingStatus.ADMIN_REVIEW,
            ListingStatus.MODERATION_UNAVAILABLE,
            ListingStatus.ESCALATED,
            ListingStatus.PENDING_MODERATION,
            ListingStatus.AI_REVIEW,
            ListingStatus.EDIT_REQUIRED,
        }:
            raise ModerationError(
                "INVALID_STATE",
                f"{previous.value} onaylanamaz — yalnızca inceleme kuyruğu",
                409,
            )
        try:
            listing_transition(previous, ListingStatus.APPROVED)
        except InvalidTransition as exc:
            raise ModerationError("CONFLICT", str(exc), 409) from exc
        conn.execute(
            """
            UPDATE listing_photos SET moderation_status = 'APPROVED'
            WHERE listing_id = ? AND moderation_version = ?
            """,
            (listing_id, mod_version),
        )
    elif decision == ModerationDecision.DELETE:
        # Soft-delete: cancel listing; allow from most non-terminal states
        if previous in {ListingStatus.TRADED, ListingStatus.CANCELLED}:
            raise ModerationError("INVALID_STATE", "İlan zaten kapalı / takas edilmiş", 409)
        try:
            listing_transition(previous, ListingStatus.CANCELLED)
        except InvalidTransition:
            # Force cancel for staff delete even if transition matrix is narrow
            pass
    elif decision == ModerationDecision.ESCALATE:
        try:
            listing_transition(previous, ListingStatus.ESCALATED)
        except InvalidTransition as exc:
            raise ModerationError("CONFLICT", str(exc), 409) from exc
    else:
        try:
            listing_transition(previous, target)
        except InvalidTransition as exc:
            raise ModerationError("CONFLICT", str(exc), 409) from exc

    now = time.time()
    if decision == ModerationDecision.ESCALATE:
        cur = conn.execute(
            """
            UPDATE trade_listings
            SET status = ?, risk_level = ?, moderation_priority = 100,
                updated_at = ?, moderation_updated_at = ?, moderation_reason = ?,
                version = version + 1
            WHERE id = ? AND version = ?
            """,
            (
                ListingStatus.ESCALATED.value,
                RiskLevel.CRITICAL.value,
                now,
                now,
                reason[:500],
                listing_id,
                version,
            ),
        )
        if cur.rowcount != 1:
            raise ModerationError("CONFLICT", "Eşzamanlı moderasyon kararı çakışması", 409)
    else:
        cur = conn.execute(
            """
            UPDATE trade_listings
            SET status = ?, updated_at = ?, moderation_updated_at = ?,
                approved_at = CASE WHEN ? = 'APPROVED' THEN ? ELSE approved_at END,
                approved_by = CASE WHEN ? = 'APPROVED' THEN ? ELSE approved_by END,
                moderation_reason = ?,
                version = version + 1
            WHERE id = ? AND version = ?
            """,
            (
                target.value,
                now,
                now,
                target.value,
                now,
                target.value,
                actor_id,
                reason[:500],
                listing_id,
                version,
            ),
        )
        if cur.rowcount != 1:
            raise ModerationError("CONFLICT", "Eşzamanlı moderasyon kararı çakışması", 409)

    if decision == ModerationDecision.SUSPEND_USER:
        conn.execute(
            "UPDATE users SET suspended = 1, user_risk_score = COALESCE(user_risk_score, 0) + 25 WHERE id = ?",
            (listing["owner_id"],),
        )
        # Kill active sessions so suspended tokens cannot keep calling APIs
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (listing["owner_id"],))

    # Close open assignments for this listing
    conn.execute(
        """
        UPDATE moderation_assignments
        SET status = 'DONE', updated_at = ?
        WHERE listing_id = ? AND status IN ('OPEN', 'IN_PROGRESS')
        """,
        (now, listing_id),
    )

    conn.execute(
        """
        INSERT INTO moderation_decisions(
          listing_id, moderation_version, moderator_id, moderator_role,
          previous_status, new_status, decision, reason,
          ai_result, ai_confidence, correlation_id, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            listing_id,
            mod_version,
            actor_id,
            actor_role,
            previous.value,
            target.value,
            decision.value,
            reason[:500],
            listing.get("ai_result"),
            listing.get("ai_confidence"),
            correlation_id,
            now,
        ),
    )
    db.audit(
        conn,
        actor_id=actor_id,
        action=f"moderation.{decision.value.lower()}",
        entity="listing",
        entity_id=listing_id,
        detail=db.dumps(
            {
                "previous_status": previous.value,
                "new_status": target.value,
                "reason": reason,
                "moderation_version": mod_version,
                "ai_result": listing.get("ai_result"),
                "ai_confidence": listing.get("ai_confidence"),
            }
        ),
        correlation_id=correlation_id,
    )
    row2 = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    db.sync_dual_status(conn, listing_id, legacy_status=target.value)
    invalidate_listing(listing_id)
    invalidate_public_listings()
    return dict(row2)


# Backward-compatible alias
def apply_superadmin_decision(
    conn,
    *,
    listing_id: int,
    actor_id: int,
    actor_role: str,
    decision: ModerationDecision,
    reason: str = "",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return apply_moderation_decision(
        conn,
        listing_id=listing_id,
        actor_id=actor_id,
        actor_role=actor_role,
        decision=decision,
        reason=reason,
        correlation_id=correlation_id,
    )


def remoderate_after_edit(
    conn,
    *,
    listing_id: int,
    actor_id: int,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Critical field edit → bump moderation_version and re-enter PENDING_MODERATION."""
    correlation_id = correlation_id or str(uuid.uuid4())
    row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    if not row:
        raise ModerationError("LISTING_NOT_FOUND", "Listing yok", 404)
    listing = dict(row)
    previous = normalize_listing_status(listing["status"])
    if previous in {ListingStatus.RESERVED, ListingStatus.TRADED}:
        raise ModerationError("NOT_EDITABLE", "Kilitli listing düzenlenemez", 409)
    new_mod = int(listing.get("moderation_version") or 1) + 1
    now = time.time()
    conn.execute(
        """
        UPDATE trade_listings SET
          status = ?,
          moderation_version = ?,
          approved_at = NULL,
          approved_by = NULL,
          ai_result = NULL,
          ai_confidence = NULL,
          updated_at = ?,
          moderation_updated_at = ?,
          version = version + 1
        WHERE id = ?
        """,
        (ListingStatus.PENDING_MODERATION.value, new_mod, now, now, listing_id),
    )
    db.sync_dual_status(
        conn,
        listing_id,
        moderation_status="PENDING_MODERATION",
        inventory_status="AVAILABLE",
        legacy_status=ListingStatus.PENDING_MODERATION.value,
    )
    db.audit(
        conn,
        actor_id=actor_id,
        action="moderation.reset_after_edit",
        entity="listing",
        entity_id=listing_id,
        detail=f"moderation_version={new_mod}",
        correlation_id=correlation_id,
    )
    return run_ai_premoderation(conn, listing_id=listing_id, correlation_id=correlation_id)


def user_status_message(status: str) -> str:
    s = normalize_listing_status(status)
    return {
        ListingStatus.DRAFT: "Taslak kaydedildi. Yayınlamak için tamamlayıp gönderin.",
        ListingStatus.PENDING_MODERATION: (
            "İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor."
        ),
        ListingStatus.AI_REVIEW: (
            "İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor."
        ),
        ListingStatus.ADMIN_REVIEW: (
            "İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor."
        ),
        ListingStatus.MODERATION_UNAVAILABLE: (
            "İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor."
        ),
        ListingStatus.APPROVED: "İlanınız yayında — ana sayfada görünür.",
        ListingStatus.ACTIVE: "İlanınız yayında — ana sayfada görünür.",
        ListingStatus.REJECTED: "İçeriğiniz Change X kurallarına uygun bulunmadı.",
        ListingStatus.EDIT_REQUIRED: "İçeriğinizde düzenleme gerekiyor.",
        ListingStatus.ESCALATED: (
            "İlanınız incelemede. Ana sayfada görünmez; İlanlarım’da duruyor."
        ),
        ListingStatus.SUSPENDED: "İçeriğiniz askıya alındı.",
        ListingStatus.RESERVED: "Takas rezervinde.",
        ListingStatus.TRADED: "Takas tamamlandı.",
        ListingStatus.CANCELLED: (
            "İlan silindi / yayından kaldırıldı. Kayıt İlanlarım’da arşivde kalır."
        ),
        ListingStatus.EXPIRED: "İlan süresi doldu.",
    }.get(s, "Durum güncellendi.")


def assert_listing_approved_for_trade(row: dict[str, Any]) -> None:
    status = normalize_listing_status(row.get("status"))
    if status not in {ListingStatus.APPROVED, ListingStatus.ACTIVE}:
        from ..engine import DomainError

        raise DomainError(
            "LISTING_NOT_APPROVED",
            f"İlan #{row.get('id')} onaylı değil ({status.value}). "
            "Teklif için yalnızca onaylanmış ilanlar kullanılabilir.",
            409,
        )
