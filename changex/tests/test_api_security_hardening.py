"""GÖREV 05 — API security regression (authn/authz/IDOR/upload/CORS/rate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from changex.app import db
from changex.app.main import UPLOAD_DIR, _CORS_CREDENTIALS, _CORS_ORIGINS
from changex.app.moderation import apply_superadmin_decision
from changex.app.states import ModerationDecision, UserRole
from changex.tests.helpers import (
    auth,
    ensure_superadmin_id,
    make_listing,
    promote_admin,
    register,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PNG = (FIXTURES / "sample.png").read_bytes()
JPG = (FIXTURES / "sample.jpg").read_bytes()


def _upload(client, token: str, data: bytes = PNG, name: str = "a.png", ctype: str = "image/png"):
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": (name, data, ctype)},
    )
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _sa(client):
    from changex.app.db import DEFAULT_SUPERADMIN_PASSWORD, DEFAULT_SUPERADMIN_USERNAME

    return client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    ).json()


# ---------------------------------------------------------------------------
# Matrix helpers: unauthenticated / non-owner / owner / admin
# ---------------------------------------------------------------------------


def test_listing_read_matrix(client):
    owner = register(client, "sec_read_o")
    other = register(client, "sec_read_x")
    admin = register(client, "sec_read_a")
    promote_admin(admin["user"]["id"])
    url = _upload(client, owner["token"])
    pending = make_listing(
        client, owner["token"], "SecPending", approve=False, photo_urls=[url]
    )
    approved = make_listing(
        client, owner["token"], "SecApproved", approve=True, photo_urls=[url]
    )
    lid_p, lid_a = pending["id"], approved["id"]

    # Unauthenticated: approved OK, pending 404
    assert client.get(f"/api/listings/{lid_a}").status_code == 200
    assert client.get(f"/api/listings/{lid_p}").status_code == 404

    # Non-owner: same
    assert client.get(f"/api/listings/{lid_a}", headers=auth(other["token"])).status_code == 200
    assert client.get(f"/api/listings/{lid_p}", headers=auth(other["token"])).status_code == 404

    # Owner: both OK
    assert client.get(f"/api/listings/{lid_p}", headers=auth(owner["token"])).status_code == 200

    # Admin: pending OK
    assert client.get(f"/api/listings/{lid_p}", headers=auth(admin["token"])).status_code == 200


def test_listing_update_matrix_idor(client):
    owner = register(client, "sec_upd_o")
    other = register(client, "sec_upd_x")
    admin = register(client, "sec_upd_a")
    promote_admin(admin["user"]["id"])
    url = _upload(client, owner["token"])
    listing = make_listing(
        client, owner["token"], "SecUpd", approve=False, photo_urls=[url]
    )
    lid = listing["id"]

    # Unauthenticated
    r = client.patch(f"/api/listings/{lid}", json={"title": "hack"})
    assert r.status_code == 401

    # Non-owner IDOR
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(other["token"]),
        json={"title": "stolen"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"

    # Owner OK
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(owner["token"]),
        json={"title": "owner-ok"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "owner-ok"

    # Admin OK
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(admin["token"]),
        json={"title": "admin-ok"},
    )
    assert r.status_code == 200


def test_listing_delete_cancel_matrix(client):
    owner = register(client, "sec_del_o")
    other = register(client, "sec_del_x")
    url = _upload(client, owner["token"])
    listing = make_listing(
        client, owner["token"], "SecDel", approve=False, photo_urls=[url]
    )
    lid = listing["id"]

    # No HTTP DELETE route
    assert client.delete(f"/api/listings/{lid}").status_code in {405, 404}

    # Unauthenticated cancel
    assert client.post(f"/api/listings/{lid}/cancel").status_code == 401

    # Non-owner cannot cancel
    r = client.post(f"/api/listings/{lid}/cancel", headers=auth(other["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"

    # Owner can soft-delete
    r = client.post(f"/api/listings/{lid}/cancel", headers=auth(owner["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CANCELLED"

    # Non-owner still cannot read cancelled
    assert client.get(f"/api/listings/{lid}", headers=auth(other["token"])).status_code == 404


def test_photo_upload_and_delete_idor(client):
    owner = register(client, "sec_ph_o")
    other = register(client, "sec_ph_x")
    url1 = _upload(client, owner["token"])
    url2 = _upload(client, owner["token"], JPG, "b.jpg", "image/jpeg")
    listing = make_listing(
        client, owner["token"], "SecPhoto", approve=False, photo_urls=[url1, url2]
    )
    lid = listing["id"]

    # Unauthenticated upload
    r = client.post(
        "/api/uploads/image",
        files={"file": ("x.png", PNG, "image/png")},
    )
    assert r.status_code == 401

    # Other cannot attach their upload onto owner's listing
    other_url = _upload(client, other["token"])
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(other["token"]),
        json={"photo_urls": [other_url]},
    )
    assert r.status_code == 403

    # Other cannot remove owner's photos via PATCH
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(other["token"]),
        json={"photo_urls": [url1]},
    )
    assert r.status_code == 403

    # Owner cannot attach other's upload
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(owner["token"]),
        json={"photo_urls": [url1, other_url]},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "UPLOAD_NOT_OWNED"

    # Owner can remove own photo
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(owner["token"]),
        json={"photo_urls": [url1]},
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls")
    assert photos == [url1]


def test_upload_path_traversal_and_filename_injection(client):
    u = register(client, "sec_trav")
    # Path traversal / absolute / nested names ignored — uuid storage only
    evil_names = [
        "../../../etc/passwd.png",
        "..\\..\\windows\\system32\\x.png",
        "/tmp/evil.png",
        "a/../../b.png",
        "ok\x00.png",
    ]
    for name in evil_names:
        r = client.post(
            "/api/uploads/image",
            headers=auth(u["token"]),
            files={"file": (name, PNG, "image/png")},
        )
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert url.startswith("/uploads/")
        assert ".." not in url
        assert "/" not in url[len("/uploads/") :]
        fname = url.rsplit("/", 1)[-1]
        assert (UPLOAD_DIR / fname).is_file()
        assert UPLOAD_DIR.resolve() in (UPLOAD_DIR / fname).resolve().parents


def test_upload_mime_mismatch_uses_sniffed_extension(client):
    u = register(client, "sec_mime")
    # PNG bytes labeled as jpeg / weird filename → stored as .png
    r = client.post(
        "/api/uploads/image",
        headers=auth(u["token"]),
        files={"file": ("photo.jpg", PNG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["url"].endswith(".png")
    assert r.json()["content_type"] == "image/png"


def test_upload_rejects_non_image_and_oversize(client):
    u = register(client, "sec_badup")
    r = client.post(
        "/api/uploads/image",
        headers=auth(u["token"]),
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    huge = b"\x89PNG\r\n\x1a\n" + b"x" * (8 * 1024 * 1024 + 10)
    r = client.post(
        "/api/uploads/image",
        headers=auth(u["token"]),
        files={"file": ("big.png", huge, "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_admin_endpoints_matrix(client):
    user = register(client, "sec_adm_u")
    admin = register(client, "sec_adm_a")
    promote_admin(admin["user"]["id"])
    sa = _sa(client)

    for path in (
        "/api/admin/stats",
        "/api/admin/moderation/queue",
        "/api/admin/panel",
        "/api/admin/staff",
    ):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth(user["token"])).status_code == 403
        assert client.get(path, headers=auth(admin["token"])).status_code == 200

    # Role assign: admin cannot, superadmin can
    target = register(client, "sec_adm_t")
    r = client.post(
        f"/api/admin/users/{target['user']['id']}/role",
        headers=auth(admin["token"]),
        json={"role": "moderator"},
    )
    assert r.status_code == 403
    r = client.post(
        f"/api/admin/users/{target['user']['id']}/role",
        headers=auth(sa["token"]),
        json={"role": "moderator"},
    )
    assert r.status_code == 200, r.text


def test_moderation_delete_non_owner_blocked_for_user(client):
    owner = register(client, "sec_mdel_o")
    other = register(client, "sec_mdel_x")
    url = _upload(client, owner["token"])
    listing = make_listing(
        client, owner["token"], "SecMDel", approve=False, photo_urls=[url]
    )
    r = client.post(
        f"/api/admin/moderation/{listing['id']}/decision",
        headers=auth(other["token"]),
        json={"decision": "DELETE", "reason": "nope"},
    )
    assert r.status_code == 403


def test_logout_revokes_token(client):
    u = register(client, "sec_logout")
    token = u["token"]
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    r = client.post("/api/auth/logout", headers=auth(token))
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_suspended_login_blocked_and_sessions_revoked(client):
    victim = register(client, "sec_sus_v")
    url = _upload(client, victim["token"])
    listing = make_listing(
        client, victim["token"], "SecSus", approve=False, photo_urls=[url]
    )
    token = victim["token"]
    actor = ensure_superadmin_id()
    with db.connect() as conn:
        with db.immediate_tx(conn):
            apply_superadmin_decision(
                conn,
                listing_id=listing["id"],
                actor_id=actor,
                actor_role=UserRole.SUPERADMIN.value,
                decision=ModerationDecision.SUSPEND_USER,
                reason="abuse",
            )
    # Existing token dead
    assert client.get("/api/auth/me", headers=auth(token)).status_code in {401, 403}
    # Fresh login blocked
    r = client.post(
        "/api/auth/login",
        json={"username": "sec_sus_v", "password": "pass12"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "USER_SUSPENDED"


def test_failed_login_is_audited(client):
    register(client, "sec_fail")
    client.post("/api/auth/login", json={"username": "sec_fail", "password": "wrong"})
    with db.connect() as conn:
        row = conn.execute(
            "SELECT action FROM audit_logs WHERE action = 'login.failed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None


def test_cors_wildcard_does_not_enable_credentials():
    assert _CORS_ORIGINS == ["*"] or isinstance(_CORS_ORIGINS, list)
    if _CORS_ORIGINS == ["*"]:
        assert _CORS_CREDENTIALS is False


def test_rate_limit_detail_does_not_leak_internal_key(client, monkeypatch):
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    # Re-enable real rate limit (load_client / client may still use real _rate_limit)
    for i in range(30):
        r = client.post(
            "/api/auth/register",
            json={"username": f"sec_rl_{i}_{i}", "password": "pass12"},
        )
        if r.status_code == 429:
            detail = r.json()["detail"]
            assert detail["code"] == "RATE_LIMIT"
            assert "key" not in detail
            return
    pytest.fail("expected RATE_LIMIT")


def test_password_hash_is_pbkdf2_and_legacy_still_verifies():
    modern = db.hash_password("pass12")
    assert modern.startswith("pbkdf2$")
    assert db.verify_password("pass12", modern)
    legacy = "abcd1234$" + __import__("hashlib").sha256(b"abcd1234:pass12").hexdigest()
    assert db.verify_password("pass12", legacy)
    assert db.needs_rehash(legacy) is True
    assert db.needs_rehash(modern) is False


def test_me_response_never_includes_password_hash(client):
    u = register(client, "sec_me")
    r = client.get("/api/auth/me", headers=auth(u["token"]))
    assert r.status_code == 200
    body = r.json()
    assert "password_hash" not in body
    assert "password" not in body


def test_generic_trade_transition_blocked_for_parties(client):
    a = register(client, "sec_tr_a")
    b = register(client, "sec_tr_b")
    want = make_listing(client, a["token"], "WantSec", approve=True)
    give = make_listing(client, b["token"], "GiveSec", approve=True)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [give["id"]],
        },
    )
    assert offer.status_code == 200, offer.text
    tid = offer.json()["id"]
    r = client.post(
        f"/api/trades/{tid}/transition",
        headers=auth(b["token"]),
        json={"target_state": "DISPUTED", "note": "nope"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "USE_DEDICATED_ENDPOINT"


def test_path_traversal_photo_url_rejected_on_create(client):
    u = register(client, "sec_purl")
    r = client.post(
        "/api/listings",
        headers=auth(u["token"]),
        json={
            "title": "Evil",
            "description": "x",
            "category": "Elektronik",
            "photo_urls": ["../../etc/passwd", "https://evil.test/x.png"],
            "items": [
                {"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}
            ],
        },
    )
    # Non-/uploads/ URLs fail ownership / invalid
    assert r.status_code in {400, 403}
