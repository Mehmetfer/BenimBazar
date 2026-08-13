"""End-to-end listing image pipeline: upload → store → DB → relation → API → approve → render."""

from __future__ import annotations

from pathlib import Path

from changex.app import db
from changex.tests.helpers import approve_listing, auth, make_listing, register

# Minimal valid 1x1 PNG
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

JPEG = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
    ]
    + [8] * 64
    + [
        0xFF,
        0xC0,
        0x00,
        0x0B,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        0x01,
        0x11,
        0x00,
        0xFF,
        0xC4,
        0x00,
        0x14,
        0x00,
        0x01,
    ]
    + [0] * 15
    + [0x08, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01]
    + [0] * 15
    + [0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7F, 0xFF, 0xD9]
)


def _upload(client, token: str, data: bytes, name: str, ctype: str) -> str:
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": (name, data, ctype)},
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("/uploads/")
    return url


def test_scenario_a_create_single_image_persists_after_approve_and_refresh(client):
    """Select→Upload→Validate→Store→DB→Relation→API→Render→Refresh."""
    u = register(client, "img_a_owner")
    url = _upload(client, u["token"], PNG, "a.png", "image/png")

    # Store on disk
    fname = url.rsplit("/", 1)[-1]
    disk = Path(db.DATA_DIR) / "uploads" / fname
    assert disk.exists() and disk.stat().st_size > 0

    # Static serve
    img = client.get(url)
    assert img.status_code == 200
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

    listing = make_listing(
        client, u["token"], "PhotoA", approve=False, photo_urls=[url]
    )
    lid = listing["id"]
    assert url in (listing.get("photo_urls") or []) or url in (
        listing.get("all_photo_urls") or []
    )

    # Relation row
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT url, moderation_status FROM listing_photos WHERE listing_id=?",
            (lid,),
        ).fetchall()
    assert any(r["url"] == url for r in rows)

    # Owner mine sees photo before approve
    mine = client.get("/api/listings/mine", headers=auth(u["token"]))
    assert mine.status_code == 200
    mine_row = next(x for x in mine.json()["listings"] if x["id"] == lid)
    assert url in mine_row["photo_urls"] or url in mine_row.get("all_photo_urls", [])

    # Public feed must NOT show pending
    pub = client.get("/api/listings").json()["listings"]
    assert not any(x["id"] == lid for x in pub)

    # Approve → public photos
    approve_listing(client, lid)
    pub2 = client.get("/api/listings").json()["listings"]
    row = next(x for x in pub2 if x["id"] == lid)
    assert url in row["photo_urls"]

    # Anon detail + refresh static
    det = client.get(f"/api/listings/{lid}")
    assert det.status_code == 200
    assert url in det.json()["photo_urls"]
    again = client.get(url)
    assert again.status_code == 200 and len(again.content) > 0


def test_scenario_b_edit_add_photo_keeps_old_and_binds_new(client):
    u = register(client, "img_b_owner")
    url1 = _upload(client, u["token"], PNG, "old.png", "image/png")
    listing = make_listing(
        client, u["token"], "PhotoB", approve=True, photo_urls=[url1]
    )
    lid = listing["id"]

    url2 = _upload(client, u["token"], JPEG, "new.jpg", "image/jpeg")
    # Absolute URL must normalize on PATCH
    abs2 = f"http://example.test{url2}"
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [url1, abs2]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    photos = body.get("all_photo_urls") or body.get("photo_urls") or []
    assert url1 in photos
    assert url2 in photos
    assert not any(p.startswith("http://example.test") for p in photos)

    # DB trade_listings.photo_urls
    with db.connect() as conn:
        row = conn.execute(
            "SELECT photo_urls FROM trade_listings WHERE id=?", (lid,)
        ).fetchone()
        stored = db.loads(row["photo_urls"], [])
    assert url1 in stored and url2 in stored


def test_scenario_c_remove_photo_persists_after_reload(client):
    u = register(client, "img_c_owner")
    url1 = _upload(client, u["token"], PNG, "keep.png", "image/png")
    url2 = _upload(client, u["token"], JPEG, "drop.jpg", "image/jpeg")
    listing = make_listing(
        client, u["token"], "PhotoC", approve=False, photo_urls=[url1, url2]
    )
    lid = listing["id"]

    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [url1]},
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls") or []
    assert photos == [url1]

    # Reload
    mine = client.get("/api/listings/mine", headers=auth(u["token"]))
    row = next(x for x in mine.json()["listings"] if x["id"] == lid)
    reloaded = row.get("all_photo_urls") or row.get("photo_urls") or []
    assert reloaded == [url1]
    assert url2 not in reloaded


def test_scenario_d_invalid_uploads_rejected(client):
    u = register(client, "img_d_owner")
    token = u["token"]

    # no auth
    r = client.post(
        "/api/uploads/image",
        files={"file": ("x.png", PNG, "image/png")},
    )
    assert r.status_code == 401

    # bad mime
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400

    # empty
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": ("x.png", b"", "image/png")},
    )
    assert r.status_code == 400

    # corrupt claiming png
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": ("x.png", b"notanimage", "image/png")},
    )
    assert r.status_code == 400

    # too large (>8MB)
    huge = b"\x89PNG\r\n\x1a\n" + b"x" * (8 * 1024 * 1024 + 10)
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": ("big.png", huge, "image/png")},
    )
    assert r.status_code == 400


def test_scenario_d_authz_cannot_edit_others_photos(client):
    a = register(client, "img_own_a")
    b = register(client, "img_own_b")
    url = _upload(client, a["token"], PNG, "a.png", "image/png")
    listing = make_listing(
        client, a["token"], "Owned", approve=False, photo_urls=[url]
    )
    url2 = _upload(client, b["token"], JPEG, "b.jpg", "image/jpeg")
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(b["token"]),
        json={"photo_urls": [url2]},
    )
    assert r.status_code == 403

    r = client.patch(
        "/api/listings/999999",
        headers=auth(a["token"]),
        json={"photo_urls": [url]},
    )
    assert r.status_code == 404


def test_upload_returns_relative_url_and_absolute(client):
    u = register(client, "img_rel")
    r = client.post(
        "/api/uploads/image",
        headers=auth(u["token"]),
        files={"file": ("z.png", PNG, "image/png")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["url"].startswith("/uploads/")
    assert "/uploads/" in data["absolute_url"]


def test_approved_listing_photos_survive_second_fetch(client):
    u = register(client, "img_persist")
    url = _upload(client, u["token"], PNG, "p.png", "image/png")
    listing = make_listing(
        client, u["token"], "Persist", approve=True, photo_urls=[url]
    )
    lid = listing["id"]
    for _ in range(3):
        det = client.get(f"/api/listings/{lid}")
        assert det.status_code == 200
        assert url in det.json()["photo_urls"]
        assert client.get(url).status_code == 200
