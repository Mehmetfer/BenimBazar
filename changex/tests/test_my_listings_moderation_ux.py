"""GÖREV 04 — My Listings / moderation visibility UX (API integration)."""

from __future__ import annotations

from pathlib import Path

from changex.app import db
from changex.app.moderation import apply_superadmin_decision
from changex.app.states import ModerationDecision, UserRole
from changex.tests.helpers import (
    approve_listing,
    auth,
    ensure_superadmin_id,
    make_listing,
    promote_admin,
    register,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PNG = (FIXTURES / "sample.png").read_bytes()


def _upload(client, token: str) -> str:
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": ("a.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _decide(listing_id: int, decision: ModerationDecision, reason: str = "test") -> None:
    actor = ensure_superadmin_id()
    with db.connect() as conn:
        with db.immediate_tx(conn):
            apply_superadmin_decision(
                conn,
                listing_id=listing_id,
                actor_id=actor,
                actor_role=UserRole.SUPERADMIN.value,
                decision=decision,
                reason=reason,
            )


def test_mine_shows_pending_with_owner_message_and_photos(client):
    u = register(client, "mine_pending")
    url = _upload(client, u["token"])
    listing = make_listing(
        client, u["token"], "PendingMine", approve=False, photo_urls=[url]
    )
    lid = listing["id"]
    assert listing["status"] != "APPROVED"
    assert "İlanlarım" in listing["user_message"] or "inceleme" in listing["user_message"].lower()
    assert listing.get("visibility") == "owner_only"
    assert any(p.get("url") == url for p in listing.get("photos") or [])

    mine = client.get("/api/listings/mine", headers=auth(u["token"]))
    assert mine.status_code == 200
    row = next(x for x in mine.json()["listings"] if x["id"] == lid)
    assert url in (row.get("all_photo_urls") or row.get("photo_urls") or [])
    assert row["status"] != "APPROVED"
    assert row.get("visibility") == "owner_only"

    # Public feed must hide pending
    pub = client.get("/api/listings").json()["listings"]
    assert not any(x["id"] == lid for x in pub)

    # Stranger cannot open by id
    stranger = register(client, "mine_pending_stranger")
    r = client.get(f"/api/listings/{lid}", headers=auth(stranger["token"]))
    assert r.status_code == 404
    # Owner can
    r2 = client.get(f"/api/listings/{lid}", headers=auth(u["token"]))
    assert r2.status_code == 200
    assert url in (r2.json().get("all_photo_urls") or r2.json().get("photo_urls") or [])


def test_mine_shows_approved_rejected_deleted_states(client):
    u = register(client, "mine_states")
    url_a = _upload(client, u["token"])
    url_r = _upload(client, u["token"])
    url_d = _upload(client, u["token"])

    approved = make_listing(
        client, u["token"], "StateApproved", approve=True, photo_urls=[url_a]
    )
    rejected = make_listing(
        client, u["token"], "StateRejected", approve=False, photo_urls=[url_r]
    )
    deleted = make_listing(
        client, u["token"], "StateDeleted", approve=False, photo_urls=[url_d]
    )
    _decide(rejected["id"], ModerationDecision.REJECT, reason="spam policy")
    _decide(deleted["id"], ModerationDecision.DELETE, reason="removed")

    mine = client.get("/api/listings/mine", headers=auth(u["token"])).json()["listings"]
    by_id = {x["id"]: x for x in mine}

    a = by_id[approved["id"]]
    assert a["status"] in {"APPROVED", "ACTIVE"}
    assert "yayında" in a["user_message"].lower() or "Takasa" in a["user_message"]
    assert a.get("visibility") == "public"

    r = by_id[rejected["id"]]
    assert r["status"] == "REJECTED"
    assert "uygun bulunmadı" in r["user_message"].lower()
    assert (r.get("moderation_reason") or "") != ""
    assert r.get("visibility") == "owner_only"

    d = by_id[deleted["id"]]
    assert d["status"] == "CANCELLED"
    assert "silindi" in d["user_message"].lower() or "kaldırıldı" in d["user_message"].lower()

    # Public only approved
    pub_ids = {x["id"] for x in client.get("/api/listings").json()["listings"]}
    assert approved["id"] in pub_ids
    assert rejected["id"] not in pub_ids
    assert deleted["id"] not in pub_ids

    # Soft-deleted not fetchable by anon
    assert client.get(f"/api/listings/{deleted['id']}").status_code == 404
    assert (
        client.get(
            f"/api/listings/{deleted['id']}", headers=auth(u["token"])
        ).status_code
        == 200
    )


def test_moderator_can_fetch_pending_by_id_user_cannot(client):
    owner = register(client, "mine_mod_owner")
    mod = register(client, "mine_mod_staff")
    promote_admin(mod["user"]["id"])  # admin is staff; also test moderator
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (UserRole.MODERATOR.value, mod["user"]["id"]),
        )

    url = _upload(client, owner["token"])
    listing = make_listing(
        client, owner["token"], "ModVisible", approve=False, photo_urls=[url]
    )
    lid = listing["id"]

    other = register(client, "mine_mod_other")
    assert client.get(f"/api/listings/{lid}", headers=auth(other["token"])).status_code == 404
    r = client.get(f"/api/listings/{lid}", headers=auth(mod["token"]))
    assert r.status_code == 200
    assert r.json().get("visibility") == "owner_only"


def test_create_then_mine_flow_no_vanish(client):
    """Login → create → pending → mine (integration of user journey)."""
    u = register(client, "mine_flow")
    url = _upload(client, u["token"])
    created = client.post(
        "/api/listings",
        headers=auth(u["token"]),
        json={
            "title": "Flow Pending",
            "description": "flow",
            "category": "Elektronik",
            "photo_urls": [url],
            "items": [
                {"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}
            ],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] != "APPROVED"
    assert body.get("visibility") == "owner_only"
    lid = body["id"]

    mine = client.get("/api/listings/mine", headers=auth(u["token"])).json()
    assert any(x["id"] == lid for x in mine["listings"])
    pub = client.get("/api/listings").json()["listings"]
    assert not any(x["id"] == lid for x in pub)

    approve_listing(client, lid)
    pub2 = client.get("/api/listings").json()["listings"]
    assert any(x["id"] == lid for x in pub2)
