"""CHANGE X Core V1.1 — abuse, rate-limit, value fuzz tests."""

from __future__ import annotations

import time

import pytest

from changex.app import db
from changex.app.value import ChangeValue, ChangeValueError
from changex.tests.helpers import auth, make_listing, register


def test_abuse_cannot_update_others_listing(client):
    a = register(client, "ab_a")
    b = register(client, "ab_b")
    listing = make_listing(client, a["token"], "Mine", madalyon=1)
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(b["token"]),
        json={"title": "Stolen"},
    )
    assert r.status_code == 403


def test_abuse_cannot_accept_others_trade(client):
    a = register(client, "ab2_a")
    b = register(client, "ab2_b")
    c = register(client, "ab2_c")
    want = make_listing(client, a["token"], "Want", madalyon=1)
    give = make_listing(client, b["token"], "Give", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    r = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=auth(c["token"]),
        json={},
    )
    assert r.status_code == 403


def test_abuse_cannot_cancel_others_offer(client):
    a = register(client, "ab3_a")
    b = register(client, "ab3_b")
    c = register(client, "ab3_c")
    want = make_listing(client, a["token"], "Want3", madalyon=1)
    give = make_listing(client, b["token"], "Give3", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    r = client.post(
        f"/api/trades/{offer['id']}/cancel",
        headers=auth(c["token"]),
        json={},
    )
    assert r.status_code == 403


def test_abuse_fake_and_negative_and_float_values(client):
    a = register(client, "ab4_a")
    for payload in [
        {"madalyon": -1, "dirhem": 0, "mandal": 0},
        {"madalyon": 1.5, "dirhem": 0, "mandal": 0},
        {"madalyon": 0, "dirhem": -3, "mandal": 0},
    ]:
        r = client.post(
            "/api/listings",
            headers=auth(a["token"]),
            json={
                "title": "BadVal",
                "category": "Ev",
                "items": [{"name": "x", "value": payload}],
            },
        )
        assert r.status_code in (400, 422), r.text


def test_abuse_offer_someone_elses_listing_as_offered(client):
    a = register(client, "ab5_a")
    b = register(client, "ab5_b")
    want = make_listing(client, a["token"], "Want5", madalyon=1)
    foreign = make_listing(client, a["token"], "Foreign", madalyon=1)
    r = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [foreign["id"]]},
    )
    assert r.status_code == 403


def test_abuse_expired_trade_accept(client):
    a = register(client, "ab6_a")
    b = register(client, "ab6_b")
    want = make_listing(client, a["token"], "Want6", madalyon=1)
    give = make_listing(client, b["token"], "Give6", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [give["id"]],
            "expires_in_seconds": 60,
        },
    ).json()
    with db.connect() as conn:
        conn.execute(
            "UPDATE trades SET expires_at = ? WHERE id = ?",
            (time.time() - 10, offer["id"]),
        )
    r = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=auth(a["token"]),
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "OFFER_EXPIRED"


def test_abuse_complete_twice_without_key_is_safe(client):
    a = register(client, "ab7_a")
    b = register(client, "ab7_b")
    want = make_listing(client, a["token"], "Want7", madalyon=1)
    give = make_listing(client, b["token"], "Give7", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    assert client.post(f"/api/trades/{offer['id']}/accept", headers=auth(a["token"]), json={}).status_code == 200
    r1 = client.post(f"/api/trades/{offer['id']}/complete", headers=auth(a["token"]), json={})
    r2 = client.post(f"/api/trades/{offer['id']}/complete", headers=auth(a["token"]), json={})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "COMPLETED"


def test_abuse_reuse_traded_listing(client):
    a = register(client, "ab8_a")
    b = register(client, "ab8_b")
    want = make_listing(client, a["token"], "Want8", madalyon=1)
    give = make_listing(client, b["token"], "Give8", madalyon=1)
    offer = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    client.post(f"/api/trades/{offer['id']}/accept", headers=auth(a["token"]), json={})
    client.post(f"/api/trades/{offer['id']}/complete", headers=auth(a["token"]), json={})
    # After complete, give is owned by A and TRADED — cannot offer again
    other = make_listing(client, b["token"], "Other8", madalyon=1)
    r = client.post(
        "/api/trades/offer",
        headers=auth(a["token"]),
        json={"requested_listing_ids": [other["id"]], "offered_listing_ids": [give["id"]]},
    )
    assert r.status_code == 409


def test_rate_limit_register(client, monkeypatch):
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    hit_429 = False
    for i in range(30):
        r = client.post(
            "/api/auth/register",
            json={"username": f"rl_user_{i}_{time.time_ns()}", "password": "pass12"},
        )
        if r.status_code == 429:
            hit_429 = True
            assert r.json()["detail"]["code"] == "RATE_LIMIT"
            break
    assert hit_429


def test_rate_limit_login(client, monkeypatch):
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    register(client, "rllogin")
    monkeypatch.setattr(main_mod, "_RATE", {})
    hit = False
    for _ in range(40):
        r = client.post("/api/auth/login", json={"username": "rllogin", "password": "wrong"})
        if r.status_code == 429:
            hit = True
            break
    assert hit


@pytest.mark.parametrize(
    "raw",
    [
        0,
        1,
        253,
        254,
        255,
        64515,
        64516,
        64517,
        10**15,
        -1,
        1.5,
        "12",
        "12.3",
        None,
        {"madalyon": 1, "dirhem": 0, "mandal": 0},
        {"madalyon": -1},
        {"madalyon": 1.0},
        {"bogus": True},
        "not-a-number",
        10**15 + 1,
        True,
        False,
        [],
        {},
    ],
)
def test_value_engine_fuzz(raw):
    try:
        v = ChangeValue.parse(raw)
        # Successful parses must round-trip to non-negative int canonical
        assert isinstance(v.mandal_units, int)
        assert v.mandal_units >= 0
        again = ChangeValue.from_mandal_units(v.mandal_units)
        assert again.serialize()["mandal_units"] == v.mandal_units
        assert again.serialize()["is_real_money"] is False
    except ChangeValueError:
        pass
    except Exception as exc:  # noqa: BLE001 — fuzz must only raise domain errors
        pytest.fail(f"unexpected exception for {raw!r}: {exc!r}")


def test_observability_no_secrets(client):
    from changex.app import main as main_mod

    a = register(client, "obs_user")
    client.post(
        "/api/auth/login",
        json={"username": "obs_user", "password": "pass12"},
        headers={"X-Correlation-Id": "obs-1"},
    )
    blob = str(main_mod.REQUEST_LOGS).lower()
    assert "pass12" not in blob
    assert "password" not in blob
    assert "bearer" not in blob
    # Token from register response must not appear in structured logs
    assert a["token"].lower() not in blob
