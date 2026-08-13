"""Professional admin dashboard aggregations (read-only queries)."""

from __future__ import annotations

from typing import Any

from changex.app import db


PENDING_STATUSES = (
    "PENDING_MODERATION",
    "AI_REVIEW",
    "ADMIN_REVIEW",
    "MODERATION_UNAVAILABLE",
    "EDIT_REQUIRED",
    "ESCALATED",
)


def _count(conn, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()["c"])


def dashboard_snapshot(conn) -> dict[str, Any]:
    """GENEL + MODERATION + SYSTEM + SECURITY counters for the yönetim paneli."""
    pending_in = ",".join("?" for _ in PENDING_STATUSES)
    general = {
        "total_users": _count(conn, "SELECT COUNT(*) c FROM users"),
        "active_users": _count(
            conn,
            "SELECT COUNT(*) c FROM users WHERE COALESCE(suspended,0)=0",
        ),
        "suspended_users": _count(
            conn,
            "SELECT COUNT(*) c FROM users WHERE COALESCE(suspended,0)=1",
        ),
        "total_listings": _count(conn, "SELECT COUNT(*) c FROM trade_listings"),
        "pending_listings": _count(
            conn,
            f"SELECT COUNT(*) c FROM trade_listings WHERE status IN ({pending_in})",
            PENDING_STATUSES,
        ),
        "approved_listings": _count(
            conn,
            "SELECT COUNT(*) c FROM trade_listings WHERE UPPER(status) IN ('APPROVED','ACTIVE')",
        ),
        "rejected_listings": _count(
            conn,
            "SELECT COUNT(*) c FROM trade_listings WHERE UPPER(status)='REJECTED'",
        ),
        "deleted_listings": _count(
            conn,
            "SELECT COUNT(*) c FROM trade_listings WHERE UPPER(status) IN ('DELETED','REMOVED')",
        ),
        "total_photos": _count(conn, "SELECT COUNT(*) c FROM listing_photos"),
    }

    recent_activity = [
        dict(r)
        for r in conn.execute(
            """
            SELECT id, actor_id, action, entity, entity_id, detail, created_at
            FROM audit_logs
            ORDER BY id DESC LIMIT 25
            """
        ).fetchall()
    ]

    oldest_pending = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT id, title, status, owner_id, created_at, moderation_priority
            FROM trade_listings
            WHERE status IN ({pending_in})
            ORDER BY created_at ASC
            LIMIT 20
            """,
            PENDING_STATUSES,
        ).fetchall()
    ]

    security = {
        "failed_logins_24h": _count(
            conn,
            """
            SELECT COUNT(*) c FROM audit_logs
            WHERE action IN ('auth.login_failed','login.failed','AUTH_LOGIN_FAILED')
            """,
        ),
        "unauthorized_attempts": _count(
            conn,
            """
            SELECT COUNT(*) c FROM audit_logs
            WHERE action LIKE '%unauthorized%' OR action LIKE '%forbidden%'
               OR action IN ('auth.unauthorized','security.unauthorized')
            """,
        ),
        "admin_actions": _count(
            conn,
            """
            SELECT COUNT(*) c FROM audit_logs
            WHERE action LIKE 'moderation.%'
               OR action LIKE 'admin.%'
               OR action LIKE 'role.%'
            """,
        ),
        "recent_admin_actions": [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, actor_id, action, entity, entity_id, detail, created_at
                FROM audit_logs
                WHERE action LIKE 'moderation.%'
                   OR action LIKE 'admin.%'
                   OR action LIKE 'role.%'
                ORDER BY id DESC LIMIT 20
                """
            ).fetchall()
        ],
    }

    # Storage health: uploads dir presence + row count
    uploads = db.DATA_DIR / "uploads"
    storage = {
        "uploads_dir": str(uploads),
        "uploads_dir_exists": uploads.is_dir(),
        "upload_files": len(list(uploads.glob("*"))) if uploads.is_dir() else 0,
        "listing_photo_rows": general["total_photos"],
    }

    return {
        "panel": "CHANGE_X_ADMIN_DASHBOARD",
        "general": general,
        "moderation": {
            "pending_queue": general["pending_listings"],
            "oldest_pending": oldest_pending,
            "photo_rows": general["total_photos"],
        },
        "system": {
            "database": {"ok": True, "path": str(db.DB_PATH)},
            "storage": storage,
            "api": {"ok": True},
            "recent_errors": [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, actor_id, action, entity, entity_id, detail, created_at
                    FROM audit_logs
                    WHERE action LIKE '%error%' OR action LIKE '%fail%'
                    ORDER BY id DESC LIMIT 15
                    """
                ).fetchall()
            ],
            "audit_events": recent_activity[:10],
        },
        "security": security,
        "recent_activity": recent_activity,
        "real_money": False,
        "live_trading": False,
    }


def search_admin_listings(
    conn,
    *,
    q: str = "",
    owner: str = "",
    status: str = "",
    category: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if q:
        clauses.append("(l.title LIKE ? OR l.description LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if owner:
        clauses.append("(u.username LIKE ? OR CAST(l.owner_id AS TEXT)=?)")
        params.extend([f"%{owner}%", owner])
    if status:
        clauses.append("UPPER(l.status)=UPPER(?)")
        params.append(status)
    if category:
        clauses.append("l.category LIKE ?")
        params.append(f"%{category}%")
    params.append(max(1, min(limit, 200)))
    sql = f"""
        SELECT l.*, u.username AS owner_username
        FROM trade_listings l
        LEFT JOIN users u ON u.id = l.owner_id
        WHERE {' AND '.join(clauses)}
        ORDER BY
          CASE WHEN l.status IN ({",".join("?" for _ in PENDING_STATUSES)}) THEN 0 ELSE 1 END,
          l.created_at ASC
        LIMIT ?
    """
    # pending first ordering needs pending statuses in CASE — bind them before LIMIT
    params = params[:-1] + list(PENDING_STATUSES) + [params[-1]]
    # Fix: PENDING_STATUSES used in CASE need to be in params at right place
    # Rebuild more carefully
    order_params = list(PENDING_STATUSES)
    final_params = []
    clauses2: list[str] = ["1=1"]
    if q:
        clauses2.append("(l.title LIKE ? OR l.description LIKE ?)")
        final_params.extend([f"%{q}%", f"%{q}%"])
    if owner:
        clauses2.append("(u.username LIKE ? OR CAST(l.owner_id AS TEXT)=?)")
        final_params.extend([f"%{owner}%", owner])
    if status:
        clauses2.append("UPPER(l.status)=UPPER(?)")
        final_params.append(status)
    if category:
        clauses2.append("l.category LIKE ?")
        final_params.append(f"%{category}%")
    pending_ph = ",".join("?" for _ in PENDING_STATUSES)
    sql = f"""
        SELECT l.*, u.username AS owner_username
        FROM trade_listings l
        LEFT JOIN users u ON u.id = l.owner_id
        WHERE {' AND '.join(clauses2)}
        ORDER BY
          CASE WHEN l.status IN ({pending_ph}) THEN 0 ELSE 1 END,
          l.created_at ASC
        LIMIT ?
    """
    final_params.extend(order_params)
    final_params.append(max(1, min(limit, 200)))
    return [dict(r) for r in conn.execute(sql, final_params).fetchall()]


def list_audit_logs(conn, *, limit: int = 100, action_prefix: str = "") -> list[dict[str, Any]]:
    if action_prefix:
        rows = conn.execute(
            """
            SELECT id, actor_id, action, entity, entity_id, detail, correlation_id, created_at
            FROM audit_logs
            WHERE action LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (f"{action_prefix}%", max(1, min(limit, 500))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, actor_id, action, entity, entity_id, detail, correlation_id, created_at
            FROM audit_logs
            ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [dict(r) for r in rows]
