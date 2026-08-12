"""CHANGE X Admin Panel V1 — superadmin seed, roles, assignments, onay kutusu."""

from __future__ import annotations

from changex.app import db
from changex.app.db import DEFAULT_SUPERADMIN_PASSWORD, DEFAULT_SUPERADMIN_USERNAME
from changex.app.states import UserRole
from changex.tests.helpers import auth, make_listing, promote_admin, register


def test_default_superadmin_password_resync(client, tmp_db):
    """Bootstrap account password is forced to the documented temporary password."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE",
            (db.hash_password("wrong-old-password"), DEFAULT_SUPERADMIN_USERNAME),
        )
    db.init_db(tmp_db)
    r = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "superadmin"


def test_admin_panel_bootstrap(client):
    sa = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    ).json()
    r = client.get("/api/admin/panel", headers=auth(sa["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["panel"] == "CHANGE_X_ADMIN"
    assert body["capabilities"]["unlimited"] is True
    assert body["capabilities"]["assign_roles"] is True
    assert "APPROVE" in body["actions"]
    assert "DELETE" in body["actions"]


def test_superadmin_assigns_moderator_and_task(client):
    sa = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    ).json()
    owner = register(client, "ap_owner")
    mod = register(client, "ap_mod")
    listing = make_listing(client, owner["token"], "QueueItem", approve=False)

    role_r = client.post(
        f"/api/admin/users/{mod['user']['id']}/role",
        headers=auth(sa["token"]),
        json={"role": "moderator", "note": "onaycı ata"},
    )
    assert role_r.status_code == 200, role_r.text
    assert role_r.json()["user"]["role"] == "moderator"

    asg = client.post(
        "/api/admin/assignments",
        headers=auth(sa["token"]),
        json={"listing_id": listing["id"], "assignee_id": mod["user"]["id"], "note": "incele"},
    )
    assert asg.status_code == 200, asg.text

    # Moderator login via token from register still works; role updated in DB
    mine = client.get("/api/admin/assignments/mine", headers=auth(mod["token"]))
    assert mine.status_code == 200
    assert any(a["listing_id"] == listing["id"] for a in mine.json()["assignments"])

    # Onay kutusu actions
    for decision, expect in [
        ("REQUEST_EDIT", "EDIT_REQUIRED"),
    ]:
        # recreate fresh listing for clean state — first REQUEST_EDIT
        pass

    listing2 = make_listing(client, owner["token"], "QueueItem2", approve=False)
    client.post(
        "/api/admin/assignments",
        headers=auth(sa["token"]),
        json={"listing_id": listing2["id"], "assignee_id": mod["user"]["id"]},
    )
    r_edit = client.post(
        f"/api/admin/moderation/{listing2['id']}/decision",
        headers=auth(mod["token"]),
        json={"decision": "REQUEST_EDIT", "reason": "foto net değil"},
    )
    assert r_edit.status_code == 200
    assert r_edit.json()["status"] == "EDIT_REQUIRED"

    listing3 = make_listing(client, owner["token"], "QueueItem3", approve=False)
    r_del = client.post(
        f"/api/admin/moderation/{listing3['id']}/decision",
        headers=auth(mod["token"]),
        json={"decision": "DELETE", "reason": "spam"},
    )
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "CANCELLED"

    listing4 = make_listing(client, owner["token"], "QueueItem4", approve=False)
    r_ok = client.post(
        f"/api/admin/moderation/{listing4['id']}/decision",
        headers=auth(mod["token"]),
        json={"decision": "APPROVE", "reason": "uygun"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "APPROVED"

    listing5 = make_listing(client, owner["token"], "QueueItem5", approve=False)
    r_rej = client.post(
        f"/api/admin/moderation/{listing5['id']}/decision",
        headers=auth(mod["token"]),
        json={"decision": "REJECT", "reason": "uygunsuz"},
    )
    assert r_rej.status_code == 200
    assert r_rej.json()["status"] == "REJECTED"


def test_regular_user_blocked_from_admin_panel(client):
    u = register(client, "ap_user")
    r = client.get("/api/admin/panel", headers=auth(u["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "STAFF_REQUIRED"


def test_admin_can_assign_task_but_not_roles(client):
    sa = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    ).json()
    adm = register(client, "ap_adm2")
    promote_admin(adm["user"]["id"])
    mod = register(client, "ap_mod2")
    # Superadmin makes moderator
    client.post(
        f"/api/admin/users/{mod['user']['id']}/role",
        headers=auth(sa["token"]),
        json={"role": "moderator"},
    )
    owner = register(client, "ap_own2")
    listing = make_listing(client, owner["token"], "AssignByAdmin", approve=False)
    asg = client.post(
        "/api/admin/assignments",
        headers=auth(adm["token"]),
        json={"listing_id": listing["id"], "assignee_id": mod["user"]["id"]},
    )
    assert asg.status_code == 200
    # Admin cannot assign roles
    denied = client.post(
        f"/api/admin/users/{mod['user']['id']}/role",
        headers=auth(adm["token"]),
        json={"role": "admin"},
    )
    assert denied.status_code == 403
