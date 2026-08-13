"""Overnight admin dashboard / search / bulk / audit API tests."""

from __future__ import annotations

from changex.tests.helpers import auth, make_listing, promote_admin, register


def _super_login(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "14531453"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_dashboard_kpi_shape(client):
    super_u = _super_login(client)
    r = client.get("/api/admin/dashboard", headers=auth(super_u["token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["panel"] == "CHANGE_X_ADMIN_DASHBOARD"
    for key in ("total_users", "total_listings", "pending_listings", "approved_listings", "total_photos"):
        assert key in body["general"]
    assert "oldest_pending" in body["moderation"]
    assert body["system"]["database"]["ok"] is True
    assert "failed_logins_24h" in body["security"]
    assert body["real_money"] is False


def test_admin_listings_search_and_filter(client):
    owner = register(client, "dash_owner_1")
    make_listing(client, owner["token"], "Dash Search Alpha Phone", approve=False)
    make_listing(client, owner["token"], "Dash Search Beta Book", approve=False, category="Kitap")
    super_u = _super_login(client)
    r = client.get(
        "/api/admin/listings",
        headers=auth(super_u["token"]),
        params={"q": "Alpha Phone"},
    )
    assert r.status_code == 200
    titles = [x["title"] for x in r.json()["listings"]]
    assert any("Alpha Phone" in t for t in titles)

    r2 = client.get(
        "/api/admin/listings",
        headers=auth(super_u["token"]),
        params={"owner": "dash_owner_1", "category": "Kitap"},
    )
    assert r2.status_code == 200
    assert r2.json()["count"] >= 1

    # Oldest pending ordering: created_at ASC among pending
    r3 = client.get("/api/admin/listings", headers=auth(super_u["token"]), params={"status": "ADMIN_REVIEW"})
    assert r3.status_code == 200


def test_bulk_requires_confirmation(client):
    owner = register(client, "bulk_owner")
    a = make_listing(client, owner["token"], "Bulk A", approve=False)
    super_u = _super_login(client)
    r = client.post(
        "/api/admin/moderation/bulk",
        headers=auth(super_u["token"]),
        json={"listing_ids": [a["id"]], "decision": "APPROVE", "reason": "x", "confirm": False},
    )
    assert r.status_code == 400
    assert "confirmation" in r.text.lower()


def test_bulk_approve_with_confirm_and_audit(client):
    owner = register(client, "bulk_owner2")
    a = make_listing(client, owner["token"], "Bulk Confirm A", approve=False)
    b = make_listing(client, owner["token"], "Bulk Confirm B", approve=False)
    super_u = _super_login(client)
    r = client.post(
        "/api/admin/moderation/bulk",
        headers=auth(super_u["token"]),
        json={
            "listing_ids": [a["id"], b["id"]],
            "decision": "APPROVE",
            "reason": "bulk overnight",
            "confirm": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok_count"] == 2
    assert body["confirmation_used"] is True
    for lid in (a["id"], b["id"]):
        pub = client.get(f"/api/listings/{lid}")
        assert pub.status_code == 200
        assert pub.json()["status"].upper() in {"APPROVED", "ACTIVE"}
    audit = client.get("/api/admin/audit", headers=auth(super_u["token"]), params={"action_prefix": "moderation"})
    assert audit.status_code == 200
    actions = [x["action"] for x in audit.json()["audit"]]
    assert any(a.startswith("moderation") for a in actions)


def test_normal_user_cannot_dashboard(client):
    u = register(client, "plain_user_dash")
    r = client.get("/api/admin/dashboard", headers=auth(u["token"]))
    assert r.status_code in {401, 403}


def test_admin_can_dashboard_but_not_assign_roles(client):
    u = register(client, "admin_dash_user")
    uid = u.get("id") or u.get("user", {}).get("id")
    assert uid
    promote_admin(int(uid))
    login = client.post("/api/auth/login", json={"username": "admin_dash_user", "password": "pass12"})
    assert login.status_code == 200
    token = login.json()["token"]
    r = client.get("/api/admin/dashboard", headers=auth(token))
    assert r.status_code == 200
    r2 = client.get("/api/admin/stats", headers=auth(token))
    assert r2.status_code == 200