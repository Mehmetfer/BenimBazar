"""GÖREV 02 — listing photo full stack scenarios (API + storage + DB + authz).

UI/browser coverage is separate; passing these does not imply UI pass.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from changex.app import db
from changex.app.main import UPLOAD_DIR
from changex.tests.helpers import approve_listing, auth, make_listing, register

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _upload(
    client,
    token: str,
    data: bytes,
    name: str,
    ctype: str,
    *,
    expect: int = 200,
):
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": (name, data, ctype)},
    )
    assert r.status_code == expect, r.text
    return r


def test_01_single_photo_create_detail_refresh(client):
    u = register(client, "fs_single")
    png = _load("sample.png")
    r = _upload(client, u["token"], png, "sample.png", "image/png")
    url = r.json()["url"]
    assert url.startswith("/uploads/")
    assert (UPLOAD_DIR / url.rsplit("/", 1)[-1]).exists()

    with db.connect() as conn:
        row = conn.execute(
            "SELECT uploader_id, bytes FROM media_uploads WHERE url = ?", (url,)
        ).fetchone()
    assert row is not None
    assert int(row["uploader_id"]) == int(u["user"]["id"])
    assert int(row["bytes"]) == len(png)

    listing = make_listing(
        client, u["token"], "SinglePhoto", approve=False, photo_urls=[url]
    )
    lid = listing["id"]
    assert url in (listing.get("all_photo_urls") or listing.get("photo_urls") or [])

    with db.connect() as conn:
        photos = conn.execute(
            "SELECT url FROM listing_photos WHERE listing_id=?", (lid,)
        ).fetchall()
    assert any(p["url"] == url for p in photos)

    approve_listing(client, lid)
    for _ in range(2):
        det = client.get(f"/api/listings/{lid}")
        assert det.status_code == 200
        assert url in det.json()["photo_urls"]
        img = client.get(url)
        assert img.status_code == 200
        assert img.content == png


def test_02_multiple_photos(client):
    u = register(client, "fs_multi")
    url1 = _upload(
        client, u["token"], _load("sample.png"), "a.png", "image/png"
    ).json()["url"]
    url2 = _upload(
        client, u["token"], _load("sample2.png"), "b.png", "image/png"
    ).json()["url"]
    url3 = _upload(
        client, u["token"], _load("sample.jpg"), "c.jpg", "image/jpeg"
    ).json()["url"]
    listing = make_listing(
        client,
        u["token"],
        "MultiPhoto",
        approve=True,
        photo_urls=[url1, url2, url3],
    )
    photos = listing["photo_urls"]
    assert photos == [url1, url2, url3]
    for url in photos:
        assert client.get(url).status_code == 200


def test_03_large_file_rejected(client):
    u = register(client, "fs_large")
    # >8MB with PNG magic — size gate fires before structural check
    huge = b"\x89PNG\r\n\x1a\n" + b"x" * (8 * 1024 * 1024 + 64)
    r = _upload(
        client, u["token"], huge, "huge.png", "image/png", expect=400
    )
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"
    # Fixture oversize blob also rejected (not a valid image / not under limit path)
    r2 = _upload(
        client,
        u["token"],
        _load("too_large.bin"),
        "big.bin",
        "application/octet-stream",
        expect=400,
    )
    assert r2.json()["detail"]["code"] in {"INVALID_IMAGE", "FILE_TOO_LARGE"}


def test_04_invalid_file_rejected(client):
    u = register(client, "fs_invalid")
    r = _upload(
        client,
        u["token"],
        _load("not_image.txt"),
        "note.txt",
        "text/plain",
        expect=400,
    )
    assert r.json()["detail"]["code"] == "INVALID_IMAGE"


def test_05_corrupt_image_rejected(client):
    u = register(client, "fs_corrupt")
    r = _upload(
        client,
        u["token"],
        _load("corrupt.png"),
        "corrupt.png",
        "image/png",
        expect=400,
    )
    assert r.json()["detail"]["code"] == "INVALID_IMAGE"


def test_06_upload_store_failure(client):
    u = register(client, "fs_storefail")
    png = _load("sample.png")
    with mock.patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")):
        r = _upload(
            client, u["token"], png, "fail.png", "image/png", expect=500
        )
    assert r.json()["detail"]["code"] == "UPLOAD_STORE_FAILED"


def test_07_unauthorized_upload(client):
    r = client.post(
        "/api/uploads/image",
        files={"file": ("x.png", _load("sample.png"), "image/png")},
    )
    assert r.status_code == 401


def test_08_cannot_attach_other_users_upload(client):
    a = register(client, "fs_own_a")
    b = register(client, "fs_own_b")
    url_a = _upload(
        client, a["token"], _load("sample.png"), "a.png", "image/png"
    ).json()["url"]
    url_b = _upload(
        client, b["token"], _load("sample.jpg"), "b.jpg", "image/jpeg"
    ).json()["url"]

    # B cannot PATCH A's listing at all
    listing = make_listing(
        client, a["token"], "OwnedA", approve=False, photo_urls=[url_a]
    )
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(b["token"]),
        json={"photo_urls": [url_b]},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"

    # A cannot attach B's uploaded URL onto A's listing
    r2 = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(a["token"]),
        json={"photo_urls": [url_a, url_b]},
    )
    assert r2.status_code == 403
    assert r2.json()["detail"]["code"] == "UPLOAD_NOT_OWNED"

    # A cannot create listing with B's URL
    r3 = client.post(
        "/api/listings",
        headers=auth(a["token"]),
        json={
            "title": "Steal",
            "description": "Steal",
            "category": "Elektronik",
            "photo_urls": [url_b],
            "items": [
                {"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}
            ],
        },
    )
    assert r3.status_code == 403
    assert r3.json()["detail"]["code"] == "UPLOAD_NOT_OWNED"

    # Fabricated /uploads path without media_uploads row
    r4 = client.post(
        "/api/listings",
        headers=auth(a["token"]),
        json={
            "title": "Fake",
            "description": "Fake",
            "category": "Elektronik",
            "photo_urls": ["/uploads/does-not-exist.png"],
            "items": [
                {"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}
            ],
        },
    )
    assert r4.status_code == 403
    assert r4.json()["detail"]["code"] == "UPLOAD_NOT_OWNED"


def test_09_refresh_persistence(client):
    u = register(client, "fs_refresh")
    url = _upload(
        client, u["token"], _load("sample.png"), "r.png", "image/png"
    ).json()["url"]
    listing = make_listing(
        client, u["token"], "RefreshMe", approve=True, photo_urls=[url]
    )
    lid = listing["id"]
    first = client.get(f"/api/listings/{lid}").json()
    second = client.get(f"/api/listings/{lid}").json()
    assert first["photo_urls"] == second["photo_urls"] == [url]
    assert client.get(url).content == _load("sample.png")


def test_10_reopen_app_new_session_still_sees_photos(client):
    """Simulate app kill/reopen: new auth session + fresh listing fetch."""
    u = register(client, "fs_reopen", password="reopen12")
    url = _upload(
        client, u["token"], _load("sample.png"), "re.png", "image/png"
    ).json()["url"]
    listing = make_listing(
        client, u["token"], "ReopenMe", approve=True, photo_urls=[url]
    )
    lid = listing["id"]

    # "Close app": drop token, login again
    login = client.post(
        "/api/auth/login",
        json={"username": "fs_reopen", "password": "reopen12"},
    )
    assert login.status_code == 200
    token2 = login.json()["token"]
    assert token2

    mine = client.get("/api/listings/mine", headers=auth(token2))
    assert mine.status_code == 200
    row = next(x for x in mine.json()["listings"] if x["id"] == lid)
    photos = row.get("all_photo_urls") or row.get("photo_urls") or []
    assert url in photos

    # Anonymous public detail after reopen
    det = client.get(f"/api/listings/{lid}")
    assert det.status_code == 200
    assert url in det.json()["photo_urls"]
    assert client.get(url).status_code == 200


def test_multipart_upload_registers_media_and_static(client):
    u = register(client, "fs_multipart")
    r = _upload(client, u["token"], _load("sample.jpg"), "cam.jpg", "image/jpeg")
    body = r.json()
    assert "absolute_url" in body and body["url"] in body["absolute_url"]
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM media_uploads").fetchone()["c"]
    assert int(n) >= 1
