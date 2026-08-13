"""Image upload + moderation queue discoverability helpers."""

from __future__ import annotations

from changex.app.db import DEFAULT_SUPERADMIN_PASSWORD, DEFAULT_SUPERADMIN_USERNAME
from changex.tests.helpers import auth, make_listing, register


def test_upload_image_and_attach_to_listing(client):
    u = register(client, "up_user")
    # Minimal 1x1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post(
        "/api/uploads/image",
        headers=auth(u["token"]),
        files={"file": ("dot.png", png, "image/png")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("/uploads/")
    img = client.get(url)
    assert img.status_code == 200
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

    listing = client.post(
        "/api/listings",
        headers=auth(u["token"]),
        json={
            "title": "WithPhoto",
            "category": "Elektronik",
            "photo_urls": [url],
            "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert listing.status_code == 200, listing.text
    assert url in listing.json().get("photo_urls", []) or url in listing.json().get(
        "all_photo_urls", []
    )


def test_superadmin_sees_pending_in_queue(client):
    owner = register(client, "q_owner")
    make_listing(client, owner["token"], "NeedReview", approve=False)
    sa = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    ).json()
    q = client.get("/api/admin/moderation/queue", headers=auth(sa["token"]))
    assert q.status_code == 200
    assert q.json()["count"] >= 1
    panel = client.get("/api/admin/panel", headers=auth(sa["token"]))
    assert panel.json()["stats"]["pending_moderation"] >= 1
