"""Messaging + support domain service (authorization enforced at call sites too)."""

from __future__ import annotations

import time
from typing import Any

from changex.app import db
from changex.app.messaging.safety import ContactPolicy, contact_policy, detect_contact_info
from changex.app.states import UserRole


class MessagingError(Exception):
    def __init__(self, code: str, message: str, *, http: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http = http
        self.extra = extra or {}


# Configurable soft limits (tests may monkeypatch)
RATE_MSG_PER_MINUTE = 20
RATE_CONV_PER_HOUR = 15
RATE_NEW_PEERS_PER_DAY = 30


def _now() -> float:
    return time.time()


def _record_rate(conn, user_id: int, kind: str) -> None:
    conn.execute(
        "INSERT INTO messaging_rate_events(user_id, kind, created_at) VALUES (?,?,?)",
        (user_id, kind, _now()),
    )


def _count_rate(conn, user_id: int, kind: str, since: float) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) c FROM messaging_rate_events
        WHERE user_id=? AND kind=? AND created_at>=?
        """,
        (user_id, kind, since),
    ).fetchone()
    return int(row["c"])


def _check_rates(conn, user_id: int, *, new_conversation: bool = False, peer_id: int | None = None) -> None:
    now = _now()
    if _count_rate(conn, user_id, "message", now - 60) >= RATE_MSG_PER_MINUTE:
        raise MessagingError("RATE_LIMITED", "Çok hızlı mesaj gönderiyorsunuz", http=429)
    if new_conversation:
        if _count_rate(conn, user_id, "conversation", now - 3600) >= RATE_CONV_PER_HOUR:
            raise MessagingError("RATE_LIMITED", "Saatlik konuşma limiti aşıldı", http=429)
        if peer_id is not None:
            if _count_rate(conn, user_id, f"peer:{peer_id}", now - 86400) == 0:
                if _count_rate(conn, user_id, "new_peer", now - 86400) >= RATE_NEW_PEERS_PER_DAY:
                    raise MessagingError("RATE_LIMITED", "Günlük yeni kişi mesaj limiti aşıldı", http=429)


def _is_blocked(conn, a: int, b: int) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)
        LIMIT 1
        """,
        (a, b, b, a),
    ).fetchone()
    return row is not None


def _participant_ids(conv: dict) -> set[int]:
    return {int(conv["buyer_id"]), int(conv["seller_id"])}


def _assert_participant(conv: dict, user_id: int) -> None:
    if int(user_id) not in _participant_ids(conv):
        raise MessagingError("FORBIDDEN", "Bu konuşmaya erişiminiz yok", http=403)


def _apply_contact_policy(body: str) -> tuple[str, list[dict], str | None]:
    hits = detect_contact_info(body)
    significant = [h for h in hits if h.confidence >= 0.7]
    policy = contact_policy()
    if not significant:
        return body, [], None
    payload = [h.to_dict() for h in significant]
    if policy == ContactPolicy.ALLOW:
        return body, payload, None
    if policy == ContactPolicy.WARN:
        return body, payload, "CONTACT_INFO_WARNING"
    raise MessagingError(
        "CONTACT_INFO_BLOCKED",
        "Telefon numarası / e-posta / harici iletişim bilgisi içeren mesajlar engellendi",
        http=400,
        extra={"hits": payload, "policy": policy.value},
    )


def create_or_get_listing_conversation(
    conn,
    *,
    buyer_id: int,
    listing_id: int,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    listing = conn.execute(
        "SELECT id, owner_id, title, status FROM trade_listings WHERE id=?",
        (listing_id,),
    ).fetchone()
    if not listing:
        raise MessagingError("LISTING_NOT_FOUND", "İlan bulunamadı", http=404)
    seller_id = int(listing["owner_id"])
    if seller_id == int(buyer_id):
        raise MessagingError("SELF_MESSAGE", "Kendi ilanınıza mesaj gönderemezsiniz", http=400)
    if _is_blocked(conn, buyer_id, seller_id):
        raise MessagingError("BLOCKED", "Bu kullanıcıyla mesajlaşamazsınız", http=403)

    existing = conn.execute(
        """
        SELECT * FROM conversations
        WHERE listing_id=? AND buyer_id=? AND seller_id=?
        """,
        (listing_id, buyer_id, seller_id),
    ).fetchone()
    if existing:
        return _conversation_public(conn, dict(existing), viewer_id=buyer_id)

    _check_rates(conn, buyer_id, new_conversation=True, peer_id=seller_id)
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO conversations(listing_id, buyer_id, seller_id, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?)
        """,
        (listing_id, buyer_id, seller_id, "OPEN", now, now),
    )
    cid = int(cur.lastrowid)
    _record_rate(conn, buyer_id, "conversation")
    _record_rate(conn, buyer_id, "new_peer")
    _record_rate(conn, buyer_id, f"peer:{seller_id}")
    db.audit(
        conn,
        actor_id=buyer_id,
        action="CONVERSATION_CREATED",
        entity="conversation",
        entity_id=cid,
        detail=f"listing_id={listing_id}",
        correlation_id=correlation_id,
    )
    row = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    return _conversation_public(conn, dict(row), viewer_id=buyer_id)


def send_message(
    conn,
    *,
    conversation_id: int,
    sender_id: int,
    body: str,
    correlation_id: str | None = None,
    acknowledge_contact_warning: bool = False,
) -> dict[str, Any]:
    body = (body or "").strip()
    if not body or len(body) > 4000:
        raise MessagingError("INVALID_BODY", "Mesaj 1–4000 karakter olmalı")
    conv = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if not conv:
        raise MessagingError("NOT_FOUND", "Konuşma bulunamadı", http=404)
    conv_d = dict(conv)
    _assert_participant(conv_d, sender_id)
    if conv_d.get("status") == "CLOSED":
        raise MessagingError("CLOSED", "Konuşma kapalı", http=400)
    other = int(conv_d["seller_id"] if int(sender_id) == int(conv_d["buyer_id"]) else conv_d["buyer_id"])
    if _is_blocked(conn, sender_id, other):
        raise MessagingError("BLOCKED", "Bu kullanıcıyla mesajlaşamazsınız", http=403)

    cleaned, hits, warn = _apply_contact_policy(body)
    if warn and not acknowledge_contact_warning:
        raise MessagingError(
            "CONTACT_INFO_WARNING",
            "Telefon numarası gibi görünen iletişim bilgileri tespit edildi. "
            "Göndermek için onaylayın veya metni düzenleyin.",
            http=409,
            extra={"hits": hits, "policy": contact_policy().value},
        )

    _check_rates(conn, sender_id, new_conversation=False)
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO messages(conversation_id, sender_id, body, status, created_at, delivered_at)
        VALUES (?,?,?,?,?,?)
        """,
        (conversation_id, sender_id, cleaned, "DELIVERED", now, now),
    )
    mid = int(cur.lastrowid)
    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
    _record_rate(conn, sender_id, "message")
    db.audit(
        conn,
        actor_id=sender_id,
        action="MESSAGE_SENT",
        entity="message",
        entity_id=mid,
        detail=f"conversation_id={conversation_id};len={len(cleaned)}",
        correlation_id=correlation_id,
    )
    row = conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    out = _message_public(dict(row))
    if hits:
        out["contact_hits"] = hits
        out["contact_warning_acknowledged"] = bool(acknowledge_contact_warning)
    return out


def get_conversation_for_user(conn, conversation_id: int, user_id: int) -> dict[str, Any]:
    conv = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if not conv:
        raise MessagingError("NOT_FOUND", "Konuşma bulunamadı", http=404)
    _assert_participant(dict(conv), user_id)
    return _conversation_public(conn, dict(conv), viewer_id=user_id)


def list_messages(conn, conversation_id: int, user_id: int, *, limit: int = 100) -> list[dict]:
    get_conversation_for_user(conn, conversation_id, user_id)
    rows = conn.execute(
        """
        SELECT * FROM messages
        WHERE conversation_id=? AND deleted_at IS NULL
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (conversation_id, max(1, min(limit, 200))),
    ).fetchall()
    # mark peer messages as READ
    now = _now()
    conn.execute(
        """
        UPDATE messages SET status='READ', read_at=COALESCE(read_at, ?)
        WHERE conversation_id=? AND sender_id<>? AND deleted_at IS NULL AND read_at IS NULL
        """,
        (now, conversation_id, user_id),
    )
    return [_message_public(dict(r)) for r in rows]


def inbox_for_user(conn, user_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM conversations
        WHERE buyer_id=? OR seller_id=?
        ORDER BY updated_at DESC
        LIMIT 100
        """,
        (user_id, user_id),
    ).fetchall()
    return [_conversation_public(conn, dict(r), viewer_id=user_id) for r in rows]


def block_user(conn, blocker_id: int, blocked_id: int, correlation_id: str | None = None) -> dict:
    if int(blocker_id) == int(blocked_id):
        raise MessagingError("INVALID", "Kendinizi engelleyemezsiniz")
    conn.execute(
        """
        INSERT OR IGNORE INTO user_blocks(blocker_id, blocked_id, created_at)
        VALUES (?,?,?)
        """,
        (blocker_id, blocked_id, _now()),
    )
    db.audit(
        conn,
        actor_id=blocker_id,
        action="USER_BLOCKED",
        entity="user",
        entity_id=blocked_id,
        detail="block",
        correlation_id=correlation_id,
    )
    return {"blocked_id": blocked_id, "ok": True}


def unblock_user(conn, blocker_id: int, blocked_id: int, correlation_id: str | None = None) -> dict:
    conn.execute(
        "DELETE FROM user_blocks WHERE blocker_id=? AND blocked_id=?",
        (blocker_id, blocked_id),
    )
    db.audit(
        conn,
        actor_id=blocker_id,
        action="USER_UNBLOCKED",
        entity="user",
        entity_id=blocked_id,
        detail="unblock",
        correlation_id=correlation_id,
    )
    return {"blocked_id": blocked_id, "ok": True}


def report_message(
    conn,
    *,
    message_id: int,
    reporter_id: int,
    reason: str,
    correlation_id: str | None = None,
) -> dict:
    allowed = {"SPAM", "HARASSMENT", "SCAM", "INAPPROPRIATE", "PERSONAL_INFO", "OTHER"}
    reason = (reason or "OTHER").upper()
    if reason not in allowed:
        raise MessagingError("INVALID_REASON", "Geçersiz bildirim nedeni")
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    if not msg:
        raise MessagingError("NOT_FOUND", "Mesaj bulunamadı", http=404)
    get_conversation_for_user(conn, int(msg["conversation_id"]), reporter_id)
    try:
        cur = conn.execute(
            """
            INSERT INTO message_reports(message_id, reporter_id, reason, status, created_at)
            VALUES (?,?,?,?,?)
            """,
            (message_id, reporter_id, reason, "OPEN", _now()),
        )
    except Exception as exc:  # noqa: BLE001
        raise MessagingError("ALREADY_REPORTED", "Bu mesajı zaten bildirdiniz") from exc
    rid = int(cur.lastrowid)
    db.audit(
        conn,
        actor_id=reporter_id,
        action="MESSAGE_REPORTED",
        entity="message_report",
        entity_id=rid,
        detail=f"message_id={message_id};reason={reason}",
        correlation_id=correlation_id,
    )
    return {"report_id": rid, "status": "OPEN", "reason": reason}


def list_reports_for_staff(conn, *, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.*, m.conversation_id, m.sender_id AS message_sender_id,
               substr(m.body, 1, 80) AS body_preview
        FROM message_reports r
        JOIN messages m ON m.id = r.message_id
        ORDER BY r.id DESC LIMIT ?
        """,
        (max(1, min(limit, 200)),),
    ).fetchall()
    return [dict(r) for r in rows]


def moderate_report(
    conn,
    *,
    report_id: int,
    actor_id: int,
    status: str,
    correlation_id: str | None = None,
) -> dict:
    status = status.upper()
    if status not in {"OPEN", "REVIEWING", "ACTIONED", "DISMISSED"}:
        raise MessagingError("INVALID_STATUS", "Geçersiz rapor durumu")
    conn.execute("UPDATE message_reports SET status=? WHERE id=?", (status, report_id))
    db.audit(
        conn,
        actor_id=actor_id,
        action="MESSAGE_MODERATED",
        entity="message_report",
        entity_id=report_id,
        detail=f"status={status}",
        correlation_id=correlation_id,
    )
    return {"report_id": report_id, "status": status}


def _next_support_public_id(conn) -> str:
    row = conn.execute("SELECT COUNT(*) c FROM support_tickets").fetchone()
    n = int(row["c"]) + 1
    return f"SUPPORT-{n:06d}"


def create_support_ticket(
    conn,
    *,
    user_id: int,
    subject: str,
    body: str,
    category: str = "GENERAL",
    priority: str = "NORMAL",
    attachment_url: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    subject = (subject or "").strip()[:200]
    body = (body or "").strip()
    if not subject or not body:
        raise MessagingError("INVALID", "Konu ve mesaj zorunlu")
    _, hits, warn = _apply_contact_policy(body)
    # Support may contain contact info intentionally — WARN only, never silent rewrite
    now = _now()
    public_id = _next_support_public_id(conn)
    cur = conn.execute(
        """
        INSERT INTO support_tickets(public_id, user_id, subject, category, priority, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (public_id, user_id, subject, category.upper()[:40], priority.upper()[:20], "OPEN", now, now),
    )
    tid = int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO support_messages(ticket_id, sender_id, body, attachment_url, created_at, is_staff)
        VALUES (?,?,?,?,?,0)
        """,
        (tid, user_id, body, attachment_url, now),
    )
    db.audit(
        conn,
        actor_id=user_id,
        action="SUPPORT_TICKET_CREATED",
        entity="support_ticket",
        entity_id=tid,
        detail=f"public_id={public_id};category={category}",
        correlation_id=correlation_id,
    )
    out = get_support_ticket(conn, tid, user_id=user_id, staff=False)
    if hits:
        out["contact_hits"] = hits
        out["contact_note"] = warn
    return out


def get_support_ticket(conn, ticket_id: int, *, user_id: int, staff: bool) -> dict:
    row = conn.execute("SELECT * FROM support_tickets WHERE id=?", (ticket_id,)).fetchone()
    if not row:
        raise MessagingError("NOT_FOUND", "Ticket bulunamadı", http=404)
    if not staff and int(row["user_id"]) != int(user_id):
        raise MessagingError("FORBIDDEN", "Bu ticket'a erişiminiz yok", http=403)
    msgs = conn.execute(
        "SELECT * FROM support_messages WHERE ticket_id=? ORDER BY created_at ASC",
        (ticket_id,),
    ).fetchall()
    d = dict(row)
    d["messages"] = [
        {
            "id": m["id"],
            "sender_id": m["sender_id"],
            "body": m["body"],
            "attachment_url": m["attachment_url"],
            "created_at": m["created_at"],
            "is_staff": bool(m["is_staff"]),
        }
        for m in msgs
    ]
    return d


def list_support_tickets(conn, *, user_id: int | None = None, staff: bool = False) -> list[dict]:
    if staff:
        rows = conn.execute(
            "SELECT * FROM support_tickets ORDER BY updated_at DESC LIMIT 200"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM support_tickets WHERE user_id=? ORDER BY updated_at DESC LIMIT 100",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        last = conn.execute(
            """
            SELECT body, created_at, is_staff FROM support_messages
            WHERE ticket_id=? ORDER BY id DESC LIMIT 1
            """,
            (r["id"],),
        ).fetchone()
        d["last_message"] = dict(last) if last else None
        out.append(d)
    return out


def send_support_message(
    conn,
    *,
    ticket_id: int,
    sender_id: int,
    body: str,
    is_staff: bool,
    attachment_url: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    ticket = get_support_ticket(conn, ticket_id, user_id=sender_id, staff=is_staff)
    if ticket["status"] in {"CLOSED"} and not is_staff:
        raise MessagingError("CLOSED", "Ticket kapalı")
    body = (body or "").strip()
    if not body:
        raise MessagingError("INVALID", "Mesaj boş olamaz")
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO support_messages(ticket_id, sender_id, body, attachment_url, created_at, is_staff)
        VALUES (?,?,?,?,?,?)
        """,
        (ticket_id, sender_id, body, attachment_url, now, 1 if is_staff else 0),
    )
    status = ticket["status"]
    if is_staff and status == "OPEN":
        status = "IN_PROGRESS"
    elif is_staff:
        status = "WAITING_FOR_USER"
    elif not is_staff and status == "WAITING_FOR_USER":
        status = "IN_PROGRESS"
    conn.execute(
        "UPDATE support_tickets SET status=?, updated_at=?, assignee_id=COALESCE(assignee_id, ?) WHERE id=?",
        (status, now, sender_id if is_staff else None, ticket_id),
    )
    db.audit(
        conn,
        actor_id=sender_id,
        action="SUPPORT_REPLY" if is_staff else "SUPPORT_TICKET_CREATED",
        entity="support_ticket",
        entity_id=ticket_id,
        detail=f"msg_id={cur.lastrowid};staff={int(is_staff)}",
        correlation_id=correlation_id,
    )
    return get_support_ticket(conn, ticket_id, user_id=sender_id, staff=is_staff)


def reply_support_ticket(
    conn,
    *,
    ticket_id: int,
    admin_id: int,
    body: str,
    resolve: bool = False,
    correlation_id: str | None = None,
) -> dict:
    out = send_support_message(
        conn,
        ticket_id=ticket_id,
        sender_id=admin_id,
        body=body,
        is_staff=True,
        correlation_id=correlation_id,
    )
    if resolve:
        conn.execute(
            "UPDATE support_tickets SET status='RESOLVED', updated_at=? WHERE id=?",
            (_now(), ticket_id),
        )
        db.audit(
            conn,
            actor_id=admin_id,
            action="TICKET_RESOLVED",
            entity="support_ticket",
            entity_id=ticket_id,
            detail="resolved",
            correlation_id=correlation_id,
        )
        out = get_support_ticket(conn, ticket_id, user_id=admin_id, staff=True)
    return out


def messaging_stats(conn) -> dict[str, Any]:
    def c(sql: str, params: tuple = ()) -> int:
        return int(conn.execute(sql, params).fetchone()["c"])

    return {
        "active_conversations": c("SELECT COUNT(*) c FROM conversations WHERE status='OPEN'"),
        "total_messages": c("SELECT COUNT(*) c FROM messages WHERE deleted_at IS NULL"),
        "open_support_tickets": c(
            "SELECT COUNT(*) c FROM support_tickets WHERE status IN ('OPEN','IN_PROGRESS','WAITING_FOR_USER')"
        ),
        "reported_messages": c("SELECT COUNT(*) c FROM message_reports WHERE status='OPEN'"),
        "blocked_users": c("SELECT COUNT(*) c FROM user_blocks"),
        "unread_support_waiting": c(
            "SELECT COUNT(*) c FROM support_tickets WHERE status='WAITING_FOR_USER'"
        ),
    }


def unread_count_for_user(conn, user_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) c FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE m.sender_id <> ?
          AND m.read_at IS NULL
          AND m.deleted_at IS NULL
          AND (c.buyer_id=? OR c.seller_id=?)
        """,
        (user_id, user_id, user_id),
    ).fetchone()
    return int(row["c"])


def _message_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "sender_id": row["sender_id"],
        "body": row["body"],
        "status": row["status"],
        "created_at": row["created_at"],
        "delivered_at": row.get("delivered_at"),
        "read_at": row.get("read_at"),
        "edited_at": row.get("edited_at"),
        "deleted_at": row.get("deleted_at"),
    }


def _conversation_public(conn, row: dict, *, viewer_id: int) -> dict:
    listing_title = None
    if row.get("listing_id"):
        lt = conn.execute(
            "SELECT title FROM trade_listings WHERE id=?", (row["listing_id"],)
        ).fetchone()
        listing_title = lt["title"] if lt else None
    last = conn.execute(
        """
        SELECT id, sender_id, body, created_at, status FROM messages
        WHERE conversation_id=? AND deleted_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (row["id"],),
    ).fetchone()
    peer_id = int(row["seller_id"] if int(viewer_id) == int(row["buyer_id"]) else row["buyer_id"])
    peer = conn.execute("SELECT id, username FROM users WHERE id=?", (peer_id,)).fetchone()
    unread = conn.execute(
        """
        SELECT COUNT(*) c FROM messages
        WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL AND deleted_at IS NULL
        """,
        (row["id"], viewer_id),
    ).fetchone()["c"]
    return {
        "id": row["id"],
        "listing_id": row.get("listing_id"),
        "listing_title": listing_title,
        "buyer_id": row["buyer_id"],
        "seller_id": row["seller_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "peer": {"id": peer["id"], "username": peer["username"]} if peer else None,
        # Privacy: never expose phone/email
        "last_message": dict(last) if last else None,
        "unread_count": int(unread),
    }


def is_staff_role(role: str | None) -> bool:
    return role in {
        UserRole.ADMIN.value,
        UserRole.SUPERADMIN.value,
        UserRole.MODERATOR.value,
    }
