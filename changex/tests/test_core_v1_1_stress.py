"""CHANGE X Core V1.1 — concurrency, double-spend, multi-listing race, rollback, recovery."""

from __future__ import annotations

import concurrent.futures
import time

import pytest

from changex.app import db
from changex.app.engine import accept_offer
from changex.tests.helpers import auth, make_listing, promote_admin, register


def test_concurrent_accept_same_trade_only_one_state_change(client):
    a = register(client, "ca_a")
    b = register(client, "ca_b")
    want = make_listing(client, a["token"], "WantA", madalyon=4)
    give = make_listing(client, b["token"], "GiveA", madalyon=4)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()

    def accept():
        return client.post(
            f"/api/trades/{offer['id']}/accept",
            headers=auth(a["token"]),
            json={},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: accept(), range(2)))

    ok = [r for r in results if r.status_code == 200]
    bad = [r for r in results if r.status_code != 200]
    assert len(ok) >= 1
    # Either second is CONFLICT or safe replay of ACCEPTED — never two OFFERED→ACCEPTED
    for r in ok:
        assert r.json()["status"] == "ACCEPTED"
    if bad:
        assert all(r.status_code == 409 for r in bad)

    with db.connect() as conn:
        events = conn.execute(
            """
            SELECT * FROM trade_events
            WHERE trade_id = ? AND from_state = 'OFFERED' AND to_state = 'ACCEPTED'
            """,
            (offer["id"],),
        ).fetchall()
        assert len(events) == 1
        trade = dict(conn.execute("SELECT * FROM trades WHERE id = ?", (offer["id"],)).fetchone())
        assert trade["status"] == "ACCEPTED"
        for lid in (want["id"], give["id"]):
            st = conn.execute(
                "SELECT status FROM trade_listings WHERE id = ?", (lid,)
            ).fetchone()["status"]
            assert st == "RESERVED"


def test_listing_double_spend_two_trades(client):
    owner = register(client, "ds_owner")
    b = register(client, "ds_b")
    c = register(client, "ds_c")
    shared = make_listing(client, owner["token"], "SharedX", madalyon=5)
    give_b = make_listing(client, b["token"], "FromB", madalyon=5)
    give_c = make_listing(client, c["token"], "FromC", madalyon=5)
    t1 = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [shared["id"]], "offered_listing_ids": [give_b["id"]]},
    ).json()
    t2 = client.post(
        "/api/trades/offer",
        headers=auth(c["token"]),
        json={"requested_listing_ids": [shared["id"]], "offered_listing_ids": [give_c["id"]]},
    ).json()

    def accept(tid, token):
        return client.post(f"/api/trades/{tid}/accept", headers=auth(token), json={})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        r1 = pool.submit(accept, t1["id"], owner["token"])
        r2 = pool.submit(accept, t2["id"], owner["token"])
        a1, a2 = r1.result(), r2.result()

    codes = sorted([a1.status_code, a2.status_code])
    assert codes == [200, 409]
    winners = [r.json() for r in (a1, a2) if r.status_code == 200]
    assert len(winners) == 1

    # Complete winner — ownership must not split to both B and C
    win_id = winners[0]["id"]
    done = client.post(
        f"/api/trades/{win_id}/complete",
        headers=auth(owner["token"]),
        json={},
    )
    assert done.status_code == 200
    shared_after = client.get(f"/api/listings/{shared['id']}").json()
    assert shared_after["status"] == "TRADED"
    assert shared_after["owner_id"] in {b["user"]["id"], c["user"]["id"]}


def test_multi_listing_shared_c_race(client):
    """Offers involving shared listing C — only one accept wins; no partial settlement."""
    owner_c = register(client, "ml_owner_c")
    p1 = register(client, "ml_p1")
    p2 = register(client, "ml_p2")
    a = make_listing(client, p1["token"], "LA", madalyon=1)
    b = make_listing(client, p1["token"], "LB", madalyon=1)
    c_listing = make_listing(client, owner_c["token"], "LC", madalyon=2)
    d = make_listing(client, p2["token"], "LD", madalyon=2)
    # Offer1: A+B for C; Offer2: D for C (shared C)
    offer1 = client.post(
        "/api/trades/offer",
        headers=auth(p1["token"]),
        json={"requested_listing_ids": [c_listing["id"]], "offered_listing_ids": [a["id"], b["id"]]},
    )
    assert offer1.status_code == 200, offer1.text
    offer2 = client.post(
        "/api/trades/offer",
        headers=auth(p2["token"]),
        json={"requested_listing_ids": [c_listing["id"]], "offered_listing_ids": [d["id"]]},
    )
    assert offer2.status_code == 200, offer2.text

    def accept(tid):
        return client.post(
            f"/api/trades/{tid}/accept",
            headers=auth(owner_c["token"]),
            json={},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(accept, offer1.json()["id"])
        f2 = pool.submit(accept, offer2.json()["id"])
        r1, r2 = f1.result(), f2.result()

    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]
    c_status = client.get(f"/api/listings/{c_listing['id']}").json()["status"]
    assert c_status == "RESERVED"
    accepted = r1.json() if r1.status_code == 200 else r2.json()
    if accepted["id"] == offer1.json()["id"]:
        assert client.get(f"/api/listings/{a['id']}").json()["status"] == "RESERVED"
        assert client.get(f"/api/listings/{b['id']}").json()["status"] == "RESERVED"
        assert client.get(f"/api/listings/{d['id']}").json()["status"] == "ACTIVE"
    else:
        assert client.get(f"/api/listings/{d['id']}").json()["status"] == "RESERVED"
        assert client.get(f"/api/listings/{a['id']}").json()["status"] == "ACTIVE"
        assert client.get(f"/api/listings/{b['id']}").json()["status"] == "ACTIVE"


def test_db_failure_mid_accept_rolls_back(client, tmp_db):
    a = register(client, "rb_a")
    b = register(client, "rb_b")
    want = make_listing(client, a["token"], "RBWant", madalyon=3)
    give = make_listing(client, b["token"], "RBGive", madalyon=3)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()

    def boom(stage: str):
        if stage == "after_reserve_0":
            raise RuntimeError("injected failure after first listing reserve")

    db.set_failure_hook(boom)
    try:
        with db.connect() as conn:
            with pytest.raises(RuntimeError):
                accept_offer(conn, trade_id=offer["id"], actor_id=a["user"]["id"])
    finally:
        db.set_failure_hook(None)

    with db.connect() as conn:
        trade = dict(conn.execute("SELECT * FROM trades WHERE id = ?", (offer["id"],)).fetchone())
        assert trade["status"] == "OFFERED"
        for lid in (want["id"], give["id"]):
            row = conn.execute("SELECT status FROM trade_listings WHERE id = ?", (lid,)).fetchone()
            assert row["status"] == "ACTIVE"
        # No accept audit committed
        accepts = conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action = 'offer.accept' AND entity_id = ?",
            (offer["id"],),
        ).fetchone()["c"]
        assert accepts == 0


def test_process_crash_orphan_reserved_recovered(client):
    """Simulate crash leftover: RESERVED without locking trade → recovery releases."""
    a = register(client, "cr_a")
    promote_admin(a["user"]["id"])
    listing = make_listing(client, a["token"], "Orphan", madalyon=1)
    with db.connect() as conn:
        conn.execute(
            "UPDATE trade_listings SET status = 'RESERVED', updated_at = ? WHERE id = ?",
            (time.time() - 3600, listing["id"]),
        )
    r = client.post("/api/admin/recover", headers=auth(a["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["released"] >= 1
    assert client.get(f"/api/listings/{listing['id']}").json()["status"] == "ACTIVE"


def test_sqlite_busy_stats_under_contention(client):
    db.reset_lock_stats()
    a = register(client, "lk_a")
    b = register(client, "lk_b")
    want = make_listing(client, a["token"], "LockWant", madalyon=2)
    give = make_listing(client, b["token"], "LockGive", madalyon=2)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()

    def accept():
        return client.post(
            f"/api/trades/{offer['id']}/accept",
            headers=auth(a["token"]),
            json={},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: accept(), range(8)))

    stats = dict(db.LOCK_STATS)
    assert stats["begin_immediate"] >= 1
    assert stats["commits"] >= 1
    # Under contention busy_retries may be 0 if scheduling is lucky — still valid
    assert stats["busy_failures"] == 0


def test_domain_metrics_endpoint(client):
    a = register(client, "met_a")
    b = register(client, "met_b")
    promote_admin(a["user"]["id"])
    want = make_listing(client, a["token"], "MetWant", madalyon=2)
    give = make_listing(client, b["token"], "MetGive", madalyon=2)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    client.post(f"/api/trades/{offer['id']}/accept", headers=auth(a["token"]), json={})
    client.post(f"/api/trades/{offer['id']}/complete", headers=auth(a["token"]), json={})
    r = client.get("/api/admin/metrics", headers=auth(a["token"]))
    assert r.status_code == 200
    domain = r.json()["domain"]
    assert domain["offers_total"] >= 1
    assert domain["completion_rate"] > 0
    assert "TL" not in str(r.json())
    assert r.json()["real_money"] is False


def test_correlation_id_roundtrip(client):
    a = register(client, "cid_a")
    r = client.get(
        "/api/listings",
        headers={**auth(a["token"]), "X-Correlation-Id": "test-corr-123"},
    )
    assert r.status_code == 200
    assert r.headers.get("X-Correlation-Id") == "test-corr-123"
