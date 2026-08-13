"""Admin moderation authorization matrix (TEST A–E)."""

from __future__ import annotations

from changex.tests.helpers import auth, make_listing, promote_admin, register
from changex.app import db
from changex.app.states import UserRole


def _login(client, username: str, password: str = "pass12"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _pending_id(client, token: str) -> int:
    listing = make_listing(client, token, "Auth Matrix Listing", approve=False)
    return int(listing["id"])


def test_a_superadmin_approve(client):
    owner = register(client, "matrix_owner_a")
    lid = _pending_id(client, owner["token"])
    super_u = _login(client, "superadmin", "14531453")
    r = client.post(
        f"/api/admin/moderation/{lid}/decision",
        headers=auth(super_u["token"]),
        json={"decision": "APPROVE", "reason": "test A"},
    )
    assert r.status_code == 200
    assert r.json()["status"].upper() in {"APPROVED", "ACTIVE"}


def test_b_moderator_approve_allowed_by_policy(client):
    """Current product policy: moderators MAY approve (not 403)."""
    owner = register(client, "matrix_owner_b")
    lid = _pending_id(client, owner["token"])
    mod = register(client, "matrix_mod_b")
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET role=? WHERE id=?",
            (UserRole.MODERATOR.value, mod["user"]["id"] if "user" in mod else mod.get("id")),
        )
    # resolve id
    uid = mod.get("id") or mod.get("user", {}).get("id")
    with db.connect() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (UserRole.MODERATOR.value, int(uid)))
    token = _login(client, "matrix_mod_b")["token"]
    r = client.post(
        f"/api/admin/moderation/{lid}/decision",
        headers=auth(token),
        json={"decision": "APPROVE", "reason": "test B"},
    )
    assert r.status_code == 200, r.text


def test_c_normal_user_approve_403(client):
    owner = register(client, "matrix_owner_c")
    lid = _pending_id(client, owner["token"])
    plain = register(client, "matrix_plain_c")
    r = client.post(
        f"/api/admin/moderation/{lid}/decision",
        headers=auth(plain["token"]),
        json={"decision": "APPROVE", "reason": "test C"},
    )
    assert r.status_code == 403


def test_d_unauthenticated_approve_401(client):
    owner = register(client, "matrix_owner_d")
    lid = _pending_id(client, owner["token"])
    r = client.post(
        f"/api/admin/moderation/{lid}/decision",
        json={"decision": "APPROVE", "reason": "test D"},
    )
    assert r.status_code in {401, 403}


def test_e_user_cannot_moderate_others_listing(client):
    owner = register(client, "matrix_owner_e")
    lid = _pending_id(client, owner["token"])
    other = register(client, "matrix_other_e")
    r = client.post(
        f"/api/admin/moderation/{lid}/decision",
        headers=auth(other["token"]),
        json={"decision": "REJECT", "reason": "test E"},
    )
    assert r.status_code == 403
