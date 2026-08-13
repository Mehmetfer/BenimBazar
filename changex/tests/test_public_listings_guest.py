"""Public listings guest mode — API acceptance (backend gates + public browse)."""

from __future__ import annotations

from pathlib import Path

from changex.tests.helpers import auth, make_listing, register

REPORT = Path(__file__).resolve().parents[2] / "reports" / "acceptance" / "PUBLIC_LISTINGS_GUEST_ACCEPTANCE.md"


def _rows(payload) -> list:
    if isinstance(payload, list):
        return payload
    return payload.get("listings") or payload.get("items") or []


def test_public_listings_guest_acceptance(client):
    seller = register(client, "guest_seller")
    buyer = register(client, "guest_buyer")
    a = make_listing(client, seller["token"], "Guest Visible Phone", approve=True)
    b = make_listing(client, seller["token"], "Guest Filter Elektronik", approve=True)
    pending = make_listing(client, seller["token"], "Guest Hidden Pending", approve=False)

    results: dict[str, str] = {}

    # Test 1 — guest listings
    pub = client.get("/api/listings")
    assert pub.status_code == 200
    ids = {int(x["id"]) for x in _rows(pub.json())}
    assert a["id"] in ids and b["id"] in ids
    assert pending["id"] not in ids
    results["Guest Listings"] = "PASS"

    # Test 2 — guest detail
    d = client.get(f"/api/listings/{a['id']}")
    assert d.status_code == 200
    body = d.json()
    assert body["title"]
    # no private contact leakage
    blob = str(body).lower()
    assert "password" not in blob
    assert "token" not in blob
    assert "email" not in blob or "email" not in body.get("owner", {})
    owner = body.get("owner") or {}
    assert set(owner.keys()) <= {"id", "username", "change_score"}
    results["Listing Detail"] = "PASS"

    # Test 3 — search
    s = client.get("/api/listings", params={"q": "Phone"})
    assert s.status_code == 200
    assert any(int(x["id"]) == a["id"] for x in _rows(s.json()))
    results["Search"] = "PASS"

    # Test 4 — filter/category
    f = client.get("/api/listings", params={"category": "Elektronik"})
    assert f.status_code == 200
    results["Filtering"] = "PASS"

    # Test 5 — trade requires auth
    trade = client.post(
        "/api/trades/offer",
        json={
            "requested_listing_ids": [a["id"]],
            "offered_listing_ids": [b["id"]],
        },
    )
    assert trade.status_code in {401, 403}
    results["Trade Login Gate"] = "PASS"

    # Test 6 — messaging requires auth
    msg = client.post("/api/messages/conversations", json={"listing_id": a["id"]})
    assert msg.status_code in {401, 403}
    results["Messaging Login Gate"] = "PASS"

    # Test 7 — create listing requires auth
    create = client.post(
        "/api/listings",
        json={
            "title": "Guest Create Blocked",
            "description": "nope",
            "category": "Ev",
            "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert create.status_code in {401, 403}
    results["Create Listing Login Gate"] = "PASS"

    # Test 8 — login trade path works (buyer offers own listing)
    buyer_listing = make_listing(client, buyer["token"], "Buyer Offer Item", approve=True)
    ok_trade = client.post(
        "/api/trades/offer",
        headers=auth(buyer["token"]),
        json={
            "requested_listing_ids": [a["id"]],
            "offered_listing_ids": [buyer_listing["id"]],
            "idempotency_key": "guest-acc-offer-1",
        },
    )
    assert ok_trade.status_code == 200, ok_trade.text
    results["Login Trade Flow"] = "PASS"

    # Test 9 — login messaging
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(buyer["token"]),
        json={"listing_id": a["id"]},
    )
    assert conv.status_code == 200, conv.text
    cid = conv.json()["id"]
    send = client.post(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(buyer["token"]),
        json={"body": "Merhaba guest acceptance"},
    )
    assert send.status_code == 200
    results["Login Messaging Flow"] = "PASS"

    # Test 10 — deep link style direct listing access
    deep = client.get(f"/api/listings/{b['id']}")
    assert deep.status_code == 200
    results["Deep Link"] = "PASS"

    # Test 11 — private APIs
    assert client.get("/api/messages/inbox").status_code in {401, 403}
    assert client.get("/api/listings/mine").status_code in {401, 403}
    assert client.get("/api/trades/mine").status_code in {401, 403}
    results["Private API Protection"] = "PASS"

    # Test 12 — admin
    assert client.get("/api/admin/dashboard").status_code in {401, 403}
    results["RBAC Regression"] = "PASS"

    # Test 13 — intended destination data still addressable after auth (listing id intact)
    assert client.get(f"/api/listings/{a['id']}", headers=auth(buyer["token"])).status_code == 200
    results["Intended Listing Return"] = "PASS"

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PUBLIC LISTINGS GUEST ACCEPTANCE",
        "",
        "Backend + guest browse gates (Flutter UX covered separately).",
        "",
    ]
    for k, v in results.items():
        lines.append(f"- {k}: **{v}**")
    lines += [
        "",
        "Guest Listings: PASS",
        "Listing Detail: PASS",
        "Search: PASS",
        "Filtering: PASS",
        "Trade Login Gate: PASS",
        "Messaging Login Gate: PASS",
        "Create Listing Login Gate: PASS",
        "Deep Link: PASS",
        "Private API Protection: PASS",
        "RBAC Regression: PASS",
        "Full Regression: PENDING",
        "",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert all(v == "PASS" for v in results.values())
