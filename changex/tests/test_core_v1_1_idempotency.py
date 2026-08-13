"""CHANGE X Core V1.1 — idempotency stress + lost-response retry."""

from __future__ import annotations

import pytest

from changex.app import db
from changex.app import main as main_mod
from changex.tests.helpers import auth, make_listing, register


def _clear_rate():
    main_mod._RATE.clear()


@pytest.mark.parametrize("repeats", [2, 5, 10, 50])
def test_offer_idempotency_stress(client, repeats):
    a = register(client, f"ido_a_{repeats}")
    b = register(client, f"ido_b_{repeats}")
    want = make_listing(client, a["token"], f"Want{repeats}", madalyon=1)
    give = make_listing(client, b["token"], f"Give{repeats}", madalyon=1)
    key = f"offer-key-{repeats}"
    bodies = []
    for _ in range(repeats):
        _clear_rate()
        r = client.post(
            "/api/trades/offer",
            headers=auth(b["token"]),
            json={
                "requested_listing_ids": [want["id"]],
                "offered_listing_ids": [give["id"]],
                "idempotency_key": key,
            },
        )
        assert r.status_code == 200, r.text
        bodies.append(r.json())
    ids = {b["id"] for b in bodies}
    assert len(ids) == 1
    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) c FROM trades WHERE idempotency_key = ?", (key,)
        ).fetchone()["c"]
        assert count == 1


@pytest.mark.parametrize("repeats", [2, 5, 10, 50])
def test_accept_idempotency_stress(client, repeats):
    a = register(client, f"ida_a_{repeats}")
    b = register(client, f"ida_b_{repeats}")
    want = make_listing(client, a["token"], f"AWant{repeats}", madalyon=1)
    give = make_listing(client, b["token"], f"AGive{repeats}", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    key = f"accept-key-{repeats}"
    for _ in range(repeats):
        _clear_rate()
        r = client.post(
            f"/api/trades/{offer['id']}/accept",
            headers=auth(a["token"]),
            json={"idempotency_key": key},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ACCEPTED"
    with db.connect() as conn:
        events = conn.execute(
            """
            SELECT COUNT(*) c FROM trade_events
            WHERE trade_id = ? AND from_state = 'OFFERED' AND to_state = 'ACCEPTED'
            """,
            (offer["id"],),
        ).fetchone()["c"]
        assert events == 1


@pytest.mark.parametrize("repeats", [2, 5, 10, 50])
def test_cancel_idempotency_stress(client, repeats):
    a = register(client, f"ic_a_{repeats}")
    b = register(client, f"ic_b_{repeats}")
    want = make_listing(client, a["token"], f"CWant{repeats}", madalyon=1)
    give = make_listing(client, b["token"], f"CGive{repeats}", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    key = f"cancel-key-{repeats}"
    for _ in range(repeats):
        _clear_rate()
        r = client.post(
            f"/api/trades/{offer['id']}/cancel",
            headers=auth(b["token"]),
            json={"idempotency_key": key},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "CANCELLED"
    with db.connect() as conn:
        events = conn.execute(
            """
            SELECT COUNT(*) c FROM trade_events
            WHERE trade_id = ? AND to_state = 'CANCELLED'
            """,
            (offer["id"],),
        ).fetchone()["c"]
        assert events == 1


@pytest.mark.parametrize("repeats", [2, 5, 10, 50])
def test_confirm_and_complete_idempotency_stress(client, repeats):
    a = register(client, f"ix_a_{repeats}")
    b = register(client, f"ix_b_{repeats}")
    want = make_listing(client, a["token"], f"XWant{repeats}", madalyon=1)
    give = make_listing(client, b["token"], f"XGive{repeats}", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    assert (
        client.post(
            f"/api/trades/{offer['id']}/accept",
            headers=auth(a["token"]),
            json={},
        ).status_code
        == 200
    )
    ckey = f"confirm-key-{repeats}"
    for _ in range(repeats):
        _clear_rate()
        r = client.post(
            f"/api/trades/{offer['id']}/confirm",
            headers=auth(a["token"]),
            json={"idempotency_key": ckey},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "CONFIRMED"
    pkey = f"complete-key-{repeats}"
    for _ in range(repeats):
        _clear_rate()
        r = client.post(
            f"/api/trades/{offer['id']}/complete",
            headers=auth(a["token"]),
            json={"idempotency_key": pkey},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "COMPLETED"
    with db.connect() as conn:
        completed = conn.execute(
            "SELECT COUNT(*) c FROM trades WHERE id = ? AND status = 'COMPLETED'",
            (offer["id"],),
        ).fetchone()["c"]
        assert completed == 1
        owners = {
            lid: conn.execute(
                "SELECT owner_id FROM trade_listings WHERE id = ?", (lid,)
            ).fetchone()["owner_id"]
            for lid in (want["id"], give["id"])
        }
        assert owners[want["id"]] == b["user"]["id"]
        assert owners[give["id"]] == a["user"]["id"]


def test_lost_response_retry_accept(client):
    """Backend commits; client retries same request — safe replay."""
    a = register(client, "retry_a")
    b = register(client, "retry_b")
    want = make_listing(client, a["token"], "RetryWant", madalyon=2)
    give = make_listing(client, b["token"], "RetryGive", madalyon=2)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [give["id"]],
            "idempotency_key": "offer-retry-1",
        },
    ).json()
    key = "accept-lost-response"
    first = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=auth(a["token"]),
        json={"idempotency_key": key},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=auth(a["token"]),
        json={"idempotency_key": key},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "ACCEPTED"
    with db.connect() as conn:
        assert (
            conn.execute(
                """
                SELECT COUNT(*) c FROM trade_events
                WHERE trade_id = ? AND from_state = 'OFFERED' AND to_state = 'ACCEPTED'
                """,
                (offer["id"],),
            ).fetchone()["c"]
            == 1
        )
