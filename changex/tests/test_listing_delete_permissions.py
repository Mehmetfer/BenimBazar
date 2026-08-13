"""Owner + superadmin listing soft-delete (cancel) acceptance."""

from __future__ import annotations

from changex.app.db import DEFAULT_SUPERADMIN_PASSWORD, DEFAULT_SUPERADMIN_USERNAME
from changex.tests.helpers import auth, make_listing, promote_admin, register


def _sa(client):
    r = client.post(
        "/api/auth/login",
        json={
            "username": DEFAULT_SUPERADMIN_USERNAME,
            "password": DEFAULT_SUPERADMIN_PASSWORD,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_can_delete_own_listing(client):
    owner = register(client, "del_owner")
    listing = make_listing(client, owner["token"], "Owner Delete Me", approve=True)
    lid = listing["id"]
    assert client.get(f"/api/listings/{lid}").status_code == 200

    r = client.post(f"/api/listings/{lid}/cancel", headers=auth(owner["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CANCELLED"

    # Public feed hides cancelled
    pub = client.get("/api/listings").json()
    ids = {int(x["id"]) for x in pub.get("listings") or []}
    assert lid not in ids
    assert client.get(f"/api/listings/{lid}").status_code == 404


def test_non_owner_cannot_delete(client):
    owner = register(client, "del_own2")
    other = register(client, "del_other")
    listing = make_listing(client, owner["token"], "Not Yours", approve=True)
    r = client.post(
        f"/api/listings/{listing['id']}/cancel", headers=auth(other["token"])
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"


def test_superadmin_can_delete_any_listing(client):
    owner = register(client, "del_sa_owner")
    sa = _sa(client)
    listing = make_listing(client, owner["token"], "SA Delete Target", approve=True)
    lid = listing["id"]

    r = client.post(f"/api/listings/{lid}/cancel", headers=auth(sa["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CANCELLED"
    assert client.get(f"/api/listings/{lid}").status_code == 404


def test_admin_can_delete_any_listing(client):
    owner = register(client, "del_adm_owner")
    admin = register(client, "del_adm")
    promote_admin(admin["user"]["id"])
    listing = make_listing(client, owner["token"], "Admin Delete Target", approve=True)
    r = client.post(
        f"/api/listings/{listing['id']}/cancel", headers=auth(admin["token"])
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CANCELLED"


def test_moderator_cannot_cancel_route(client):
    """Moderators use moderation DELETE; cancel route stays owner/admin/superadmin."""
    from changex.app import db
    from changex.app.states import UserRole

    owner = register(client, "del_mod_owner")
    mod = register(client, "del_mod")
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (UserRole.MODERATOR.value, mod["user"]["id"]),
        )
    listing = make_listing(client, owner["token"], "Mod Cancel Block", approve=True)
    r = client.post(
        f"/api/listings/{listing['id']}/cancel", headers=auth(mod["token"])
    )
    assert r.status_code == 403
