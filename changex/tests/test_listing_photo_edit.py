"""GÖREV 03 — listing edit / photo management (DB + storage + authz + rollback)."""

from __future__ import annotations

from pathlib import Path

import pytest

from changex.app import db, media_storage
from changex.app.main import UPLOAD_DIR
from changex.tests.helpers import auth, make_listing, promote_admin, register

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _png(name: str = "sample.png") -> bytes:
    return (FIXTURES / name).read_bytes()


def _upload(client, token: str, filename: str = "sample.png", ctype: str = "image/png") -> str:
    data = _png(filename) if filename.endswith(".png") else (FIXTURES / filename).read_bytes()
    if filename.endswith(".jpg"):
        ctype = "image/jpeg"
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": (filename, data, ctype)},
    )
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _disk(url: str) -> Path:
    return UPLOAD_DIR / url.rsplit("/", 1)[-1]


def _listing_photos(conn, listing_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT url FROM listing_photos WHERE listing_id=? ORDER BY id",
        (listing_id,),
    ).fetchall()
    return [r["url"] for r in rows]


def test_edit_add_photo_keeps_old(client):
    u = register(client, "edit_add")
    url1 = _upload(client, u["token"], "sample.png")
    listing = make_listing(
        client, u["token"], "AddPhoto", approve=True, photo_urls=[url1]
    )
    lid = listing["id"]
    url2 = _upload(client, u["token"], "sample2.png")
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [url1, url2]},
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls")
    assert photos == [url1, url2]
    assert _disk(url1).is_file()
    assert _disk(url2).is_file()
    # Refresh
    mine = client.get("/api/listings/mine", headers=auth(u["token"])).json()
    row = next(x for x in mine["listings"] if x["id"] == lid)
    reloaded = row.get("all_photo_urls") or row.get("photo_urls")
    assert reloaded == [url1, url2]


def test_edit_delete_photo_removes_db_and_storage(client):
    u = register(client, "edit_del")
    url1 = _upload(client, u["token"], "sample.png")
    url2 = _upload(client, u["token"], "sample2.png")
    listing = make_listing(
        client, u["token"], "DelPhoto", approve=False, photo_urls=[url1, url2]
    )
    lid = listing["id"]
    assert _disk(url2).is_file()

    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [url1]},
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls")
    assert photos == [url1]

    with db.connect() as conn:
        stored = db.loads(
            conn.execute(
                "SELECT photo_urls FROM trade_listings WHERE id=?", (lid,)
            ).fetchone()["photo_urls"],
            [],
        )
        assert stored == [url1]
        assert url2 not in _listing_photos(conn, lid)
        media = conn.execute(
            "SELECT deleted_at FROM media_uploads WHERE url=?", (url2,)
        ).fetchone()
        # Registry row removed after successful unlink (or soft-deleted then deleted)
        assert media is None or media["deleted_at"] is not None

    assert not _disk(url2).exists(), "removed photo must be unlinked after commit"
    assert _disk(url1).is_file()


def test_edit_replace_photos(client):
    u = register(client, "edit_rep")
    old = _upload(client, u["token"], "sample.png")
    listing = make_listing(
        client, u["token"], "Replace", approve=True, photo_urls=[old]
    )
    new = _upload(client, u["token"], "sample.jpg")
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(u["token"]),
        json={"photo_urls": [new]},
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls")
    assert photos == [new]
    assert _disk(new).is_file()
    assert not _disk(old).exists()


def test_edit_multi_photo_add_and_remove(client):
    u = register(client, "edit_multi")
    a = _upload(client, u["token"], "sample.png")
    b = _upload(client, u["token"], "sample2.png")
    c = _upload(client, u["token"], "sample.jpg")
    listing = make_listing(
        client, u["token"], "Multi", approve=False, photo_urls=[a, b]
    )
    lid = listing["id"]
    r = client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [a, c]},  # keep a, drop b, add c
    )
    assert r.status_code == 200, r.text
    photos = r.json().get("all_photo_urls") or r.json().get("photo_urls")
    assert photos == [a, c]
    assert _disk(a).is_file() and _disk(c).is_file()
    assert not _disk(b).exists()


def test_unauthorized_cannot_delete_others_photos(client):
    a = register(client, "edit_auth_a")
    b = register(client, "edit_auth_b")
    url = _upload(client, a["token"], "sample.png")
    listing = make_listing(
        client, a["token"], "Owned", approve=False, photo_urls=[url]
    )
    # B cannot PATCH A's listing
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(b["token"]),
        json={"photo_urls": [_upload(client, b["token"], "sample2.png")]},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"
    assert _disk(url).is_file()
    with db.connect() as conn:
        stored = db.loads(
            conn.execute(
                "SELECT photo_urls FROM trade_listings WHERE id=?",
                (listing["id"],),
            ).fetchone()["photo_urls"],
            [],
        )
    assert stored == [url]


def test_nonexistent_photo_url_rejected_on_attach(client):
    u = register(client, "edit_none")
    url = _upload(client, u["token"], "sample.png")
    listing = make_listing(
        client, u["token"], "NonePhoto", approve=False, photo_urls=[url]
    )
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(u["token"]),
        json={"photo_urls": [url, "/uploads/does-not-exist-abc.png"]},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "UPLOAD_NOT_OWNED"
    # Original untouched
    assert _disk(url).is_file()
    det = client.get(
        f"/api/listings/{listing['id']}", headers=auth(u["token"])
    ).json()
    photos = det.get("all_photo_urls") or det.get("photo_urls")
    assert photos == [url]


def test_empty_photo_list_rejected(client):
    u = register(client, "edit_empty")
    url = _upload(client, u["token"], "sample.png")
    listing = make_listing(
        client, u["token"], "Empty", approve=False, photo_urls=[url]
    )
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(u["token"]),
        json={"photo_urls": []},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "PHOTO_REQUIRED"
    assert _disk(url).is_file()


def test_transaction_failure_does_not_delete_storage(client):
    u = register(client, "edit_txfail")
    url1 = _upload(client, u["token"], "sample.png")
    url2 = _upload(client, u["token"], "sample2.png")
    listing = make_listing(
        client, u["token"], "TxFail", approve=False, photo_urls=[url1, url2]
    )
    lid = listing["id"]
    path2 = _disk(url2)
    assert path2.is_file()

    def boom(stage: str):
        if stage == "before_commit":
            raise RuntimeError("injected listing edit failure")

    db.set_failure_hook(boom)
    try:
        with pytest.raises(RuntimeError):
            client.patch(
                f"/api/listings/{lid}",
                headers=auth(u["token"]),
                json={"photo_urls": [url1]},
            )
    finally:
        db.set_failure_hook(None)

    # Rollback: DB + disk unchanged
    assert path2.is_file(), "physical file must survive failed transaction"
    with db.connect() as conn:
        stored = db.loads(
            conn.execute(
                "SELECT photo_urls FROM trade_listings WHERE id=?", (lid,)
            ).fetchone()["photo_urls"],
            [],
        )
        assert stored == [url1, url2]
        media = conn.execute(
            "SELECT deleted_at FROM media_uploads WHERE url=?", (url2,)
        ).fetchone()
        assert media is not None and media["deleted_at"] is None


def test_shared_url_not_deleted_while_other_listing_refs(client):
    u = register(client, "edit_share")
    shared = _upload(client, u["token"], "sample.png")
    other = _upload(client, u["token"], "sample2.png")
    l1 = make_listing(
        client, u["token"], "Share1", approve=False, photo_urls=[shared, other]
    )
    l2 = make_listing(
        client, u["token"], "Share2", approve=False, photo_urls=[shared]
    )
    # Remove shared from l1 only — still on l2
    r = client.patch(
        f"/api/listings/{l1['id']}",
        headers=auth(u["token"]),
        json={"photo_urls": [other]},
    )
    assert r.status_code == 200, r.text
    assert _disk(shared).is_file(), "must not unlink while another listing refs it"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT deleted_at FROM media_uploads WHERE url=?", (shared,)
        ).fetchone()
        assert row is not None and row["deleted_at"] is None
        assert shared in db.loads(
            conn.execute(
                "SELECT photo_urls FROM trade_listings WHERE id=?", (l2["id"],)
            ).fetchone()["photo_urls"],
            [],
        )


def test_orphan_cleanup_removes_unattached_uploads(client):
    u = register(client, "edit_orphan")
    admin = register(client, "edit_orphan_admin")
    promote_admin(admin["user"]["id"])
    orphan = _upload(client, u["token"], "sample.png")
    kept = _upload(client, u["token"], "sample2.png")
    make_listing(
        client, u["token"], "KeepOrphan", approve=False, photo_urls=[kept]
    )
    assert _disk(orphan).is_file()

    # Age gate: max_age_seconds=0 treats never-attached as immediately eligible
    r = client.post(
        "/api/admin/media/cleanup-orphans",
        headers=auth(admin["token"]),
        json={"max_age_seconds": 0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["removed"] >= 1
    assert not _disk(orphan).exists()
    assert _disk(kept).is_file()
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT id FROM media_uploads WHERE url=?", (orphan,)
            ).fetchone()
            is None
        )


def test_orphan_cleanup_unauthorized(client):
    u = register(client, "edit_orphan_user")
    r = client.post(
        "/api/admin/media/cleanup-orphans",
        headers=auth(u["token"]),
        json={"max_age_seconds": 0},
    )
    assert r.status_code == 403


def test_refresh_after_edit_persists(client):
    u = register(client, "edit_refresh")
    a = _upload(client, u["token"], "sample.png")
    b = _upload(client, u["token"], "sample2.png")
    listing = make_listing(
        client, u["token"], "RefreshEdit", approve=False, photo_urls=[a, b]
    )
    lid = listing["id"]
    client.patch(
        f"/api/listings/{lid}",
        headers=auth(u["token"]),
        json={"photo_urls": [a]},
    )
    for _ in range(3):
        mine = client.get("/api/listings/mine", headers=auth(u["token"])).json()
        row = next(x for x in mine["listings"] if x["id"] == lid)
        photos = row.get("all_photo_urls") or row.get("photo_urls")
        assert photos == [a]
        assert client.get(a).status_code == 200
        assert client.get(b).status_code == 404


def test_mark_unreferenced_never_unlinks_inside_open_tx(tmp_db):
    """Unit: soft-delete only; finalize is separate."""
    from changex.app.db import hash_password
    import time

    url = "/uploads/unit-only.png"
    path = UPLOAD_DIR / "unit-only.png"
    path.write_bytes(_png())
    with db.connect() as conn:
        with db.immediate_tx(conn):
            uid = conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?,?,?)",
                ("unit_media", hash_password("x"), time.time()),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO media_uploads(url, uploader_id, bytes, content_type, created_at)
                VALUES (?,?,?,?,?)
                """,
                (url, uid, 10, "image/png", time.time()),
            )
            marked = media_storage.mark_unreferenced_for_delete(conn, [url])
            assert marked == [url]
            # Still on disk during open tx
            assert path.is_file()
    # After commit, finalize may unlink
    stats = media_storage.finalize_storage_deletes(UPLOAD_DIR, [url])
    assert stats["removed"] == 1
    assert not path.exists()
