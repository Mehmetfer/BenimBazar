"""Shared helpers for CHANGE X tests (importable; fixtures live in conftest)."""

from __future__ import annotations

from changex.app import db
from changex.app.moderation import apply_superadmin_decision
from changex.app.states import ModerationDecision, UserRole


def register(client, username: str, password: str = "pass12"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def promote_admin(user_id: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (UserRole.ADMIN.value, user_id))


def promote_superadmin(user_id: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (UserRole.SUPERADMIN.value, user_id),
        )


def ensure_superadmin_id() -> int:
    """Create a dedicated superadmin user row (no HTTP) for direct approval."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("__superadmin__",)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET role = ?, suspended = 0 WHERE id = ?",
                (UserRole.SUPERADMIN.value, row["id"]),
            )
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,?)",
            ("__superadmin__", db.hash_password("pass12"), UserRole.SUPERADMIN.value, 0),
        )
        return int(cur.lastrowid)


def approve_listing(client, listing_id: int, super_token: str | None = None) -> dict:
    """Approve via engine (authoritative) — avoids HTTP rate limits in suites."""
    actor_id = ensure_superadmin_id()
    with db.connect() as conn:
        with db.immediate_tx(conn):
            apply_superadmin_decision(
                conn,
                listing_id=listing_id,
                actor_id=actor_id,
                actor_role=UserRole.SUPERADMIN.value,
                decision=ModerationDecision.APPROVE,
                reason="test approve",
            )
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
    assert row is not None
    assert str(row["status"]).upper() in {"APPROVED", "ACTIVE"}
    # Return public shape via API when client given
    if client is not None:
        r = client.get(f"/api/listings/{listing_id}")
        if r.status_code == 200:
            return r.json()
    return dict(row)


def make_listing(
    client,
    token: str,
    title: str,
    madalyon: int = 1,
    category: str = "Elektronik",
    *,
    approve: bool = True,
    photo_urls: list[str] | None = None,
    description: str | None = None,
):
    payload = {
        "title": title,
        "description": description if description is not None else title,
        "category": category,
        "items": [{"name": title, "value": {"madalyon": madalyon, "dirhem": 0, "mandal": 0}}],
    }
    if photo_urls is not None:
        payload["photo_urls"] = photo_urls
    r = client.post(
        "/api/listings",
        headers=auth(token),
        json=payload,
    )
    assert r.status_code == 200, r.text
    listing = r.json()
    if approve:
        if listing["status"] == "REJECTED":
            return listing
        listing = approve_listing(client, listing["id"])
    return listing
