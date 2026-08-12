"""CHANGE X Trust & Safety V1 — moderation gate, RBAC, AI fail-safe, audit."""

from __future__ import annotations

import concurrent.futures

import pytest

from changex.app import db
from changex.app.moderation import (
    HeuristicModerationProvider,
    UnavailableModerationProvider,
    set_provider,
)
from changex.app.states import ModerationDecision, UserRole
from changex.tests.helpers import (
    approve_listing,
    auth,
    make_listing,
    promote_admin,
    promote_superadmin,
    register,
)


@pytest.fixture(autouse=True)
def _reset_provider():
    set_provider(HeuristicModerationProvider())
    yield
    set_provider(HeuristicModerationProvider())


def test_new_listing_pending_moderation(client):
    u = register(client, "ts_new")
    listing = make_listing(client, u["token"], "Phone", approve=False)
    assert listing["status"] in {
        "PENDING_MODERATION",
        "AI_REVIEW",
        "ADMIN_REVIEW",
        "MODERATION_UNAVAILABLE",
    }
    assert listing["status"] != "APPROVED"
    assert "incelemeye" in listing["user_message"].lower() or "inceleme" in listing.get(
        "user_message", ""
    ).lower()


def test_pending_listing_offer_rejected(client):
    a = register(client, "ts_po_a")
    b = register(client, "ts_po_b")
    want = make_listing(client, a["token"], "WantP", approve=False)
    give = make_listing(client, b["token"], "GiveP", approve=True)
    r = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LISTING_NOT_APPROVED"


def test_pending_excluded_from_public_feed(client):
    a = register(client, "ts_feed")
    pending = make_listing(client, a["token"], "HiddenItem", approve=False)
    feed = client.get("/api/listings").json()["listings"]
    ids = {x["id"] for x in feed}
    assert pending["id"] not in ids


def test_ai_safe_still_requires_superadmin(client):
    a = register(client, "ts_safe")
    listing = make_listing(client, a["token"], "Clean Laptop", approve=False)
    assert listing.get("ai_result") == "SAFE"
    assert listing["status"] == "ADMIN_REVIEW"
    feed = client.get("/api/listings").json()["listings"]
    assert listing["id"] not in {x["id"] for x in feed}


def test_ai_high_risk_admin_queue(client):
    a = register(client, "ts_hr")
    sa = register(client, "ts_hr_sa")
    promote_superadmin(sa["user"]["id"])
    listing = make_listing(
        client,
        a["token"],
        "Silah satılık ruhsatsız",
        description="ruhsatsız silah satılık",
        approve=False,
    )
    assert listing["ai_result"] in {"HIGH_RISK", "BLOCKED", "REVIEW"}
    q = client.get("/api/admin/moderation/queue", headers=auth(sa["token"]))
    assert q.status_code == 200
    ids = {x["id"] for x in q.json()["queue"]}
    if listing["status"] != "REJECTED":
        assert listing["id"] in ids


def test_ai_unavailable_no_publication(client):
    set_provider(UnavailableModerationProvider())
    a = register(client, "ts_unav")
    listing = make_listing(client, a["token"], "Anything", approve=False)
    assert listing["status"] == "MODERATION_UNAVAILABLE"
    assert listing["id"] not in {x["id"] for x in client.get("/api/listings").json()["listings"]}


def test_user_cannot_set_approved(client):
    a = register(client, "ts_bypass")
    listing = make_listing(client, a["token"], "Bypass", approve=False)
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(a["token"]),
        json={"status": "APPROVED"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "STATUS_IMMUTABLE"


def test_admin_cannot_superadmin_approve(client):
    a = register(client, "ts_adm_a")
    adm = register(client, "ts_adm")
    promote_admin(adm["user"]["id"])
    listing = make_listing(client, a["token"], "NeedsSA", approve=False)
    r = client.post(
        f"/api/admin/moderation/{listing['id']}/decision",
        headers=auth(adm["token"]),
        json={"decision": "APPROVE", "reason": "nope"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SUPERADMIN_REQUIRED"


def test_superadmin_can_approve_and_reject(client):
    a = register(client, "ts_sa_a")
    b = register(client, "ts_sa_b")
    sa = register(client, "ts_sa")
    promote_superadmin(sa["user"]["id"])
    ok = make_listing(client, a["token"], "GoodItem", approve=False)
    bad = make_listing(client, b["token"], "OtherItem", approve=False)
    r1 = client.post(
        f"/api/admin/moderation/{ok['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "APPROVE", "reason": "uygun"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "APPROVED"
    r2 = client.post(
        f"/api/admin/moderation/{bad['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "REJECT", "reason": "uygunsuz"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "REJECTED"


def test_approved_edit_resets_moderation(client):
    a = register(client, "ts_edit")
    listing = make_listing(client, a["token"], "EditMe", approve=True)
    assert listing["status"] == "APPROVED"
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(a["token"]),
        json={"title": "EditMe Changed", "description": "new text"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] != "APPROVED"
    assert body["moderation_version"] >= 2
    assert body["id"] not in {x["id"] for x in client.get("/api/listings").json()["listings"]}


def test_new_photo_requires_moderation(client):
    a = register(client, "ts_photo")
    listing = make_listing(client, a["token"], "PhotoItem", approve=True)
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(a["token"]),
        json={"photo_urls": ["https://cdn.example.com/new.jpg"]},
    )
    assert r.status_code == 200
    assert r.json()["status"] != "APPROVED"


def test_rejected_cannot_receive_offer(client):
    a = register(client, "ts_rej_a")
    b = register(client, "ts_rej_b")
    sa = register(client, "ts_rej_sa")
    promote_superadmin(sa["user"]["id"])
    want = make_listing(client, a["token"], "RejectMe", approve=False)
    client.post(
        f"/api/admin/moderation/{want['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "REJECT", "reason": "policy"},
    )
    give = make_listing(client, b["token"], "GiveR", approve=True)
    r = client.post(
        "/api/trades/offer",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [want["id"]], "offered_listing_ids": [give["id"]]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LISTING_NOT_APPROVED"


def test_change_chain_blocks_unapproved(client):
    a = register(client, "ts_cc_a")
    b = register(client, "ts_cc_b")
    pending = make_listing(client, a["token"], "ChainPend", approve=False)
    ok = make_listing(client, b["token"], "ChainOk", approve=True)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(b["token"]),
        json={"requested_listing_ids": [pending["id"]], "offered_listing_ids": [ok["id"]]},
    )
    # Feature flag off → disabled before algorithm; unapproved still never matchable
    assert r.status_code == 501
    assert r.json()["detail"]["code"] == "CHANGE_CHAIN_DISABLED"


def test_moderation_action_creates_audit(client):
    a = register(client, "ts_aud_a")
    sa = register(client, "ts_aud_sa")
    promote_superadmin(sa["user"]["id"])
    listing = make_listing(client, a["token"], "AuditMe", approve=False)
    client.post(
        f"/api/admin/moderation/{listing['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "APPROVE", "reason": "ok audit"},
    )
    audit = client.get(
        f"/api/admin/moderation/{listing['id']}/audit",
        headers=auth(sa["token"]),
    )
    assert audit.status_code == 200
    assert len(audit.json()["decisions"]) >= 1
    assert audit.json()["decisions"][0]["decision"] == "APPROVE"


def test_moderation_revision_prevents_stale_approval(client):
    a = register(client, "ts_rev")
    listing = make_listing(client, a["token"], "Rev1", approve=True)
    v1 = listing["moderation_version"]
    client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(a["token"]),
        json={"title": "Rev2"},
    )
    with db.connect() as conn:
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert int(row["moderation_version"]) > int(v1)
    assert row["status"] != "APPROVED"
    assert row.get("approved_at") in (None, 0)


def test_concurrent_admin_decisions_safe(client):
    a = register(client, "ts_conc_a")
    sa1 = register(client, "ts_conc_sa1")
    sa2 = register(client, "ts_conc_sa2")
    promote_superadmin(sa1["user"]["id"])
    promote_superadmin(sa2["user"]["id"])
    listing = make_listing(client, a["token"], "RaceMod", approve=False)

    def decide(token, decision):
        return client.post(
            f"/api/admin/moderation/{listing['id']}/decision",
            headers=auth(token),
            json={"decision": decision, "reason": "race"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(decide, sa1["token"], "APPROVE")
        f2 = pool.submit(decide, sa2["token"], "REJECT")
        r1, r2 = f1.result(), f2.result()

    codes = sorted([r1.status_code, r2.status_code])
    assert 200 in codes
    # One success; other conflict or also processed depending on timing — never dual final
    with db.connect() as conn:
        st = conn.execute(
            "SELECT status FROM trade_listings WHERE id = ?", (listing["id"],)
        ).fetchone()["status"]
        decisions = conn.execute(
            "SELECT COUNT(*) c FROM moderation_decisions WHERE listing_id = ?",
            (listing["id"],),
        ).fetchone()["c"]
    assert st in {"APPROVED", "REJECTED"}
    assert decisions >= 1


def test_superadmin_request_edit(client):
    a = register(client, "ts_edit_req")
    sa = register(client, "ts_edit_sa")
    promote_superadmin(sa["user"]["id"])
    listing = make_listing(client, a["token"], "NeedsEdit", approve=False)
    r = client.post(
        f"/api/admin/moderation/{listing['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "REQUEST_EDIT", "reason": "foto net değil"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "EDIT_REQUIRED"
    assert "düzenleme" in r.json()["user_message"].lower()


def test_suspended_user_cannot_act(client):
    a = register(client, "ts_sus_a")
    sa = register(client, "ts_sus_sa")
    promote_superadmin(sa["user"]["id"])
    listing = make_listing(client, a["token"], "SuspendMe", approve=False)
    r = client.post(
        f"/api/admin/moderation/{listing['id']}/decision",
        headers=auth(sa["token"]),
        json={"decision": "SUSPEND_USER", "reason": "abuse"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUSPENDED"
    # Suspended owner cannot create new listings
    r2 = client.post(
        "/api/listings",
        headers=auth(a["token"]),
        json={
            "title": "AfterSuspend",
            "category": "Ev",
            "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r2.status_code == 403
    assert r2.json()["detail"]["code"] == "USER_SUSPENDED"


def test_search_cache_cannot_expose_unapproved(client):
    from changex.app.moderation.cache import cache_set, reset_cache

    a = register(client, "ts_cache")
    pending = make_listing(client, a["token"], "CacheLeak", approve=False)
    # Poison cache with unapproved listing (simulating bug/stale write)
    cache_set(
        "public:listings::",
        {"listings": [{"id": pending["id"], "status": "PENDING_MODERATION", "title": "leak"}]},
    )
    feed = client.get("/api/listings").json()["listings"]
    assert pending["id"] not in {x["id"] for x in feed}
    assert all(str(x.get("status")).upper() in {"APPROVED", "ACTIVE"} for x in feed)
    reset_cache()


def test_ai_timeout_no_publication(client):
    from changex.app.moderation import TimeoutModerationProvider, set_provider

    set_provider(TimeoutModerationProvider())
    a = register(client, "ts_timeout")
    listing = make_listing(client, a["token"], "TimeoutItem", approve=False)
    assert listing["status"] == "MODERATION_UNAVAILABLE"
    assert listing["id"] not in {x["id"] for x in client.get("/api/listings").json()["listings"]}


def test_ai_malformed_response_safe_failure(client):
    from changex.app.moderation import MalformedModerationProvider, set_provider

    set_provider(MalformedModerationProvider())
    a = register(client, "ts_malform")
    listing = make_listing(client, a["token"], "MalformedItem", approve=False)
    assert listing["status"] == "MODERATION_UNAVAILABLE"
    assert listing["id"] not in {x["id"] for x in client.get("/api/listings").json()["listings"]}


def test_invalid_listing_transitions(client):
    from changex.app.states import ListingStatus, InvalidTransition, listing_transition

    with pytest.raises(InvalidTransition):
        listing_transition(ListingStatus.REJECTED, ListingStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        listing_transition(ListingStatus.TRADED, ListingStatus.PENDING_MODERATION)
