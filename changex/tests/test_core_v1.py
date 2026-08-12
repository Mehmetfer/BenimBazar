"""CHANGE X Core V1 tests — value, listings, offers, concurrency, states, atomicity."""

from __future__ import annotations

import concurrent.futures
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from changex.app import db
from changex.app.states import InvalidTransition, ListingStatus, TradeState, transition
from changex.app.value import (
    MANDAL_PER_DIRHEM,
    MANDAL_PER_MADALYON,
    ChangeValue,
    ChangeValueError,
    value_gap,
)


@pytest.fixture()
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "test.db"
        monkeypatch.setattr(db, "DB_PATH", path)
        db.init_db(path)
        yield path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    from changex.app.main import app

    with TestClient(app) as c:
        yield c


def _register(client, username: str, password: str = "pass12"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _listing(client, token: str, title: str, madalyon: int = 1, category: str = "Elektronik"):
    r = client.post(
        "/api/listings",
        headers=_auth(token),
        json={
            "title": title,
            "description": title,
            "category": category,
            "items": [{"name": title, "value": {"madalyon": madalyon, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Value tests ----------


def test_conversion_constants():
    assert MANDAL_PER_DIRHEM == 254
    assert MANDAL_PER_MADALYON == 64516


@pytest.mark.parametrize(
    "units,mad,dirh,man",
    [
        (0, 0, 0, 0),
        (1, 0, 0, 1),
        (253, 0, 0, 253),
        (254, 0, 1, 0),
        (255, 0, 1, 1),
        (64516, 1, 0, 0),
        (64516 + 1, 1, 0, 1),
        (254 * 253, 0, 253, 0),
        (254 * 254, 1, 0, 0),  # 254 Dirhem = 1 Madalyon
    ],
)
def test_normalize_edges(units, mad, dirh, man):
    v = ChangeValue.from_mandal_units(units)
    assert v.madalyon == mad
    assert v.dirhem == dirh
    assert v.mandal == man
    assert v.mandal_units == units


def test_from_units_and_add_sub_compare():
    a = ChangeValue.from_units(madalyon=8, dirhem=40, mandal=12)
    assert a.mandal_units == 8 * 64516 + 40 * 254 + 12
    b = ChangeValue.from_units(dirhem=1)
    c = a.add(b)
    assert c.mandal_units == a.mandal_units + 254
    assert a.compare(b) > 0
    assert a.subtract(ChangeValue.from_units(mandal=12)).mandal_units == a.mandal_units - 12


def test_negative_and_float_rejected():
    with pytest.raises(ChangeValueError):
        ChangeValue.from_units(madalyon=-1)
    with pytest.raises(ChangeValueError):
        ChangeValue.from_units(dirhem=-5)
    with pytest.raises(ChangeValueError):
        ChangeValue(-2)
    with pytest.raises(ChangeValueError):
        ChangeValue.parse(1.5)
    with pytest.raises(ChangeValueError):
        ChangeValue.parse("12.3")
    with pytest.raises(ChangeValueError):
        ChangeValue.parse({"madalyon": 1.0})


def test_overflow():
    with pytest.raises(ChangeValueError):
        ChangeValue.from_mandal_units(10**15 + 1)
    big = ChangeValue.from_mandal_units(10**15)
    with pytest.raises(ChangeValueError):
        big.add(ChangeValue.from_mandal_units(1))


def test_gap_display_no_money_words_as_currency_amount():
    a = ChangeValue.from_units(madalyon=100)
    b = ChangeValue.from_units(madalyon=93)
    g = value_gap(a, b)
    assert g["exact_match"] is False
    assert g["value_gap"]["madalyon"] == 7
    assert "TL" not in g["value_gap_display"]
    assert "USD" not in g["value_gap_display"]
    assert "Madalyon" in g["value_gap_display"]


def test_format_serialize():
    v = ChangeValue.from_units(madalyon=1, dirhem=2, mandal=3)
    s = v.serialize()
    assert s["is_real_money"] is False
    assert s["mandal_units"] == 64516 + 508 + 3
    assert "Madalyon" in v.format()


# ---------- State machine ----------


def test_valid_transitions():
    assert transition(TradeState.OFFERED, TradeState.ACCEPTED) == TradeState.ACCEPTED
    assert transition(TradeState.ACCEPTED, TradeState.CONFIRMED) == TradeState.CONFIRMED
    assert transition(TradeState.CONFIRMED, TradeState.IN_TRANSFER) == TradeState.IN_TRANSFER
    assert transition(TradeState.IN_TRANSFER, TradeState.DELIVERED) == TradeState.DELIVERED
    assert transition(TradeState.DELIVERED, TradeState.COMPLETED) == TradeState.COMPLETED


@pytest.mark.parametrize(
    "cur,nxt",
    [
        (TradeState.COMPLETED, TradeState.OFFERED),
        (TradeState.CANCELLED, TradeState.ACCEPTED),
        (TradeState.EXPIRED, TradeState.ACCEPTED),
        (TradeState.COMPLETED, TradeState.CANCELLED),
    ],
)
def test_invalid_transitions(cur, nxt):
    with pytest.raises(InvalidTransition):
        transition(cur, nxt)


# ---------- API / listing / offer ----------


def test_register_login_and_negative_listing_rejected(client):
    u = _register(client, "neguser")
    r = client.post(
        "/api/listings",
        headers=_auth(u["token"]),
        json={
            "title": "Bad",
            "category": "Ev",
            "items": [{"name": "x", "value": {"madalyon": -1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 422 or r.status_code == 400


def test_float_value_rejected(client):
    u = _register(client, "floatuser")
    r = client.post(
        "/api/listings",
        headers=_auth(u["token"]),
        json={
            "title": "BadFloat",
            "category": "Ev",
            "items": [{"name": "x", "value": {"madalyon": 1.5, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 422


def test_listing_create_ownership_update(client):
    a = _register(client, "owner1")
    b = _register(client, "other1")
    listing = _listing(client, a["token"], "Telefon", madalyon=8)
    assert listing["status"] == "ACTIVE"
    assert listing["owner_id"] == a["user"]["id"]
    assert listing["mandal_units"] == 8 * 64516
    assert listing["version"] == 1

    # other cannot update
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=_auth(b["token"]),
        json={"title": "Hack"},
    )
    assert r.status_code == 403

    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=_auth(a["token"]),
        json={"title": "Telefon Pro"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Telefon Pro"
    assert r.json()["version"] == 2


def test_offer_gap_and_self_trade_blocked(client):
    a = _register(client, "alice_g")
    b = _register(client, "bob_g")
    want = _listing(client, a["token"], "WantPhone", madalyon=100)
    give = _listing(client, b["token"], "GiveBike", madalyon=93)
    # self trade
    r = client.post(
        "/api/trades/offer",
        headers=_auth(a["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [want["id"]],
        },
    )
    assert r.status_code in (400, 403)

    r = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [give["id"]],
            "idempotency_key": "offer-1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value_gap"]["madalyon"] == 7
    assert body["exact_match"] is False
    assert "TL" not in body["value_gap_display"]

    # idempotent recreate
    r2 = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [give["id"]],
            "idempotency_key": "offer-1",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == body["id"]


def test_multi_listing_offer_server_recalc(client):
    a = _register(client, "alice_m")
    b = _register(client, "bob_m")
    want = _listing(client, a["token"], "Laptop", madalyon=10)
    o1 = _listing(client, b["token"], "Kitap", madalyon=4)
    o2 = _listing(client, b["token"], "Saat", madalyon=6)
    r = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={
            "requested_listing_ids": [want["id"]],
            "offered_listing_ids": [o1["id"], o2["id"]],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["exact_match"] is True
    assert r.json()["calculated_value"]["offered"]["madalyon"] == 10


def test_unauthorized_cancel(client):
    a = _register(client, "alice_u")
    b = _register(client, "bob_u")
    c = _register(client, "carol_u")
    want = _listing(client, a["token"], "Camera", madalyon=2)
    give = _listing(client, b["token"], "Lens", madalyon=2)
    offer = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()
    r = client.post(
        f"/api/trades/{offer['id']}/cancel",
        headers=_auth(c["token"]),
        json={},
    )
    assert r.status_code == 403


def test_accept_complete_atomic_and_idempotent(client):
    a = _register(client, "alice_c")
    b = _register(client, "bob_c")
    want = _listing(client, a["token"], "PhoneX", madalyon=5)
    give = _listing(client, b["token"], "BikeX", madalyon=5)
    offer = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    ).json()

    acc = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=_auth(a["token"]),
        json={"idempotency_key": "acc-1"},
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["status"] == "ACCEPTED"
    # listings reserved
    w = client.get(f"/api/listings/{want['id']}").json()
    g = client.get(f"/api/listings/{give['id']}").json()
    assert w["status"] == "RESERVED"
    assert g["status"] == "RESERVED"

    acc2 = client.post(
        f"/api/trades/{offer['id']}/accept",
        headers=_auth(a["token"]),
        json={"idempotency_key": "acc-1"},
    )
    assert acc2.status_code == 200
    assert acc2.json()["id"] == offer["id"]

    done = client.post(
        f"/api/trades/{offer['id']}/complete",
        headers=_auth(a["token"]),
        json={"idempotency_key": "cmp-1"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"

    # ownership swapped + TRADED
    w2 = client.get(f"/api/listings/{want['id']}").json()
    g2 = client.get(f"/api/listings/{give['id']}").json()
    assert w2["status"] == "TRADED"
    assert g2["status"] == "TRADED"
    assert w2["owner_id"] == b["user"]["id"]
    assert g2["owner_id"] == a["user"]["id"]

    done2 = client.post(
        f"/api/trades/{offer['id']}/complete",
        headers=_auth(a["token"]),
        json={"idempotency_key": "cmp-1"},
    )
    assert done2.status_code == 200
    assert done2.json()["status"] == "COMPLETED"


def test_concurrent_accept_only_one_wins(client):
    a = _register(client, "alice_race")
    b = _register(client, "bob_race")
    c = _register(client, "carol_race")
    want = _listing(client, a["token"], "RaceItem", madalyon=3)
    give_b = _listing(client, b["token"], "BItem", madalyon=3)
    give_c = _listing(client, c["token"], "CItem", madalyon=3)
    offer_b = client.post(
        "/api/trades/offer",
        headers=_auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give_b["id"]]},
    ).json()
    offer_c = client.post(
        "/api/trades/offer",
        headers=_auth(c["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give_c["id"]]},
    ).json()

    def accept(oid, token):
        return client.post(
            f"/api/trades/{oid}/accept",
            headers=_auth(token),
            json={},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(accept, offer_b["id"], a["token"])
        f2 = pool.submit(accept, offer_c["id"], a["token"])
        r1, r2 = f1.result(), f2.result()

    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200
    assert codes[1] == 409
    winners = [r for r in (r1, r2) if r.status_code == 200]
    assert winners[0].json()["status"] == "ACCEPTED"
    listing = client.get(f"/api/listings/{want['id']}").json()
    assert listing["status"] == "RESERVED"


def test_guest_can_list_but_not_create(client):
    r = client.get("/api/listings")
    assert r.status_code == 200
    r = client.post(
        "/api/listings",
        json={
            "title": "Nope",
            "category": "Ev",
            "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 401


def test_health_no_money_domain(client):
    h = client.get("/api/health").json()
    assert h["real_money"] is False
    assert h["canonical"] == "mandal_units"
    blob = str(h).lower()
    assert "try" not in blob
    assert "usd" not in blob
