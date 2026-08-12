"""CHANGE X Exchange Graph V1 — infrastructure tests (no Chain algorithm)."""

from __future__ import annotations

import pytest

from changex.app import db
from changex.app.domain_status import InventoryStatus, ModerationStatus, TradePreference
from changex.app.matching import (
    CHANGE_CHAIN_ENABLED,
    MatchCandidate,
    NullScoreProvider,
    WantValidationError,
    get_compatibility,
    is_chain_candidate,
    is_public_matchable,
    matchability_report,
    validate_structured_want,
)
from changex.app.matching.config import CHANGE_CHAIN_ENABLED as FLAG
from changex.app.matching.wants import validate_value_tolerance
from changex.tests.helpers import approve_listing, auth, make_listing, register


def test_chain_opt_in_default_false(client):
    u = register(client, "eg_opt_def")
    listing = make_listing(client, u["token"], "OptDefault", approve=True)
    assert listing.get("chain_opt_in") is False
    assert listing.get("trade_preference") == "DIRECT_ONLY"
    r = client.get("/api/matching/preferences", headers=auth(u["token"]))
    assert r.status_code == 200
    assert r.json()["preferences"]["chain_opt_in"] is False
    assert r.json()["feature_flags"]["CHANGE_CHAIN_ENABLED"] is False


def test_chain_opt_in_enable_disable(client):
    u = register(client, "eg_opt_ed")
    r = client.patch(
        "/api/matching/preferences",
        headers=auth(u["token"]),
        json={"chain_opt_in": True, "trade_preference": "CHAIN_ALLOWED"},
    )
    assert r.status_code == 200
    assert r.json()["preferences"]["chain_opt_in"] is True
    assert r.json()["preferences"]["trade_preference"] == "CHAIN_ALLOWED"
    r2 = client.patch(
        "/api/matching/preferences",
        headers=auth(u["token"]),
        json={"chain_opt_in": False, "trade_preference": "DIRECT_ONLY"},
    )
    assert r2.json()["preferences"]["chain_opt_in"] is False


def test_structured_want_validation(client):
    ok = validate_structured_want(
        wanted_categories=["Elektronik"],
        wanted_value_min=100,
        wanted_value_max=200,
    )
    assert ok["wanted_categories"] == ["Elektronik"]
    with pytest.raises(WantValidationError):
        validate_structured_want(wanted_value_min=500, wanted_value_max=10)


def test_invalid_want_rejected(client):
    u = register(client, "eg_badwant")
    r = client.post(
        "/api/listings",
        headers=auth(u["token"]),
        json={
            "title": "BadWant",
            "category": "Elektronik",
            "wanted_value_min": {"madalyon": 2, "dirhem": 0, "mandal": 0},
            "wanted_value_max": {"madalyon": 1, "dirhem": 0, "mandal": 0},
            "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_WANT"


def test_approved_listing_matchable(client):
    u = register(client, "eg_ok")
    listing = make_listing(client, u["token"], "Matchable", approve=True)
    with db.connect() as conn:
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert is_public_matchable(row)
    assert row["moderation_status"] == ModerationStatus.APPROVED.value
    assert row["inventory_status"] == InventoryStatus.AVAILABLE.value


def test_unapproved_listing_not_matchable(client):
    u = register(client, "eg_pend")
    listing = make_listing(client, u["token"], "NotYet", approve=False)
    with db.connect() as conn:
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert not is_public_matchable(row)
    assert not is_chain_candidate(row)


@pytest.mark.parametrize(
    "force_status,expect_inv",
    [
        ("RESERVED", InventoryStatus.RESERVED),
        ("TRADED", InventoryStatus.TRADED),
        ("CANCELLED", InventoryStatus.CANCELLED),
        ("SUSPENDED", None),
    ],
)
def test_blocked_inventory_not_matchable(client, force_status, expect_inv):
    u = register(client, f"eg_blk_{force_status}")
    listing = make_listing(client, u["token"], f"Blk{force_status}", approve=True)
    with db.connect() as conn:
        if force_status == "SUSPENDED":
            conn.execute(
                "UPDATE trade_listings SET status=?, moderation_status=?, inventory_status=? WHERE id=?",
                ("SUSPENDED", "SUSPENDED", "AVAILABLE", listing["id"]),
            )
        else:
            conn.execute(
                "UPDATE trade_listings SET status=?, inventory_status=?, moderation_status=? WHERE id=?",
                (force_status, force_status if force_status != "CANCELLED" else "CANCELLED", "APPROVED", listing["id"]),
            )
            if force_status == "CANCELLED":
                conn.execute(
                    "UPDATE trade_listings SET moderation_status=? WHERE id=?",
                    ("REJECTED", listing["id"]),
                )
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert not is_public_matchable(row)
    assert not is_chain_candidate(row)


def test_direct_only_not_chain_candidate(client):
    u = register(client, "eg_direct")
    listing = make_listing(client, u["token"], "DirectOnly", approve=True)
    with db.connect() as conn:
        conn.execute(
            "UPDATE trade_listings SET chain_opt_in=1, trade_preference='DIRECT_ONLY' WHERE id=?",
            (listing["id"],),
        )
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert is_public_matchable(row)
    assert not is_chain_candidate(row)


def test_chain_opt_in_allows_candidate_structurally(client):
    u = register(client, "eg_chainok")
    listing = make_listing(
        client,
        u["token"],
        "ChainOk",
        approve=True,
    )
    # enable via create fields — patch listing not for chain_opt without remotion of critical
    with db.connect() as conn:
        conn.execute(
            "UPDATE trade_listings SET chain_opt_in=1, trade_preference='CHAIN_ALLOWED' WHERE id=?",
            (listing["id"],),
        )
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert is_chain_candidate(row)
    # Algorithm still disabled
    assert FLAG is False


def test_structured_value_range_and_tolerance():
    assert validate_value_tolerance(0) == 0
    assert validate_value_tolerance(100) == 100
    with pytest.raises(WantValidationError):
        validate_value_tolerance(-1)


def test_category_compatibility_validation():
    compat = get_compatibility()
    assert compat.compatible("Elektronik", "Elektronik")
    assert not compat.compatible("Elektronik", "Spor")
    assert compat.policy_version.startswith("CHANGE_X_CATEGORY")


def test_stale_listing_excluded(client):
    u = register(client, "eg_stale")
    listing = make_listing(client, u["token"], "Stale", approve=True)
    with db.connect() as conn:
        conn.execute(
            "UPDATE trade_listings SET status='EXPIRED', inventory_status='EXPIRED' WHERE id=?",
            (listing["id"],),
        )
        row = dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing["id"],)).fetchone())
    assert not is_public_matchable(row)


def test_moderation_revision_invalidates_matchability(client):
    u = register(client, "eg_rev")
    listing = make_listing(client, u["token"], "RevMatch", approve=True)
    assert is_public_matchable(_row(listing["id"]))
    client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(u["token"]),
        json={"title": "RevMatch2"},
    )
    row = _row(listing["id"])
    assert not is_public_matchable(row)
    assert int(row["moderation_version"]) >= 2


def _row(listing_id: int) -> dict:
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone())


def test_feature_flag_disabled(client):
    assert CHANGE_CHAIN_ENABLED is False
    u = register(client, "eg_flag")
    a = make_listing(client, u["token"], "FlagA", approve=True)
    b = make_listing(client, u["token"], "FlagB", approve=True)
    # Need second user for offer shape — use same ids in stub
    r = client.post(
        "/api/change-chain/match",
        headers=auth(u["token"]),
        json={"requested_listing_ids": [a["id"]], "offered_listing_ids": [b["id"]]},
    )
    assert r.status_code == 501
    assert r.json()["detail"]["code"] == "CHANGE_CHAIN_DISABLED"


def test_unauthorized_preference_update_rejected(client):
    r = client.patch("/api/matching/preferences", json={"chain_opt_in": True})
    assert r.status_code == 401


def test_user_cannot_alter_moderation_status(client):
    u = register(client, "eg_mod_bypass")
    listing = make_listing(client, u["token"], "NoModHack", approve=False)
    r = client.patch(
        f"/api/listings/{listing['id']}",
        headers=auth(u["token"]),
        json={"moderation_status": "APPROVED"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "STATUS_IMMUTABLE"


def test_no_private_pii_in_preferences_api(client):
    u = register(client, "eg_pii")
    r = client.get("/api/matching/preferences", headers=auth(u["token"]))
    blob = str(r.json()).lower()
    assert "password" not in blob
    assert "token" not in blob
    assert "email" not in blob
    assert "phone" not in blob
    assert u["token"].lower() not in blob


def test_migration_dual_status_compatibility(client):
    u = register(client, "eg_mig")
    listing = make_listing(client, u["token"], "MigDual", approve=True)
    row = _row(listing["id"])
    assert row["moderation_status"] == "APPROVED"
    assert row["inventory_status"] == "AVAILABLE"
    assert row["status"] == "APPROVED"


def test_match_candidate_contract_no_materialization():
    c = MatchCandidate(source_listing_id=1, target_listing_id=2, scores=NullScoreProvider().score_pair({}, {}))
    d = c.to_dict()
    assert d["graph_edge_materialized"] is False
    assert d["chain_algorithm"] == "NOT_IMPLEMENTED"
    assert d["total_score"] == 0.0


def test_matchability_api(client):
    u = register(client, "eg_mapi")
    listing = make_listing(client, u["token"], "ApiMatch", approve=True)
    r = client.get(f"/api/listings/{listing['id']}/matchability", headers=auth(u["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["public_matchable"] is True
    assert body["chain_feature_enabled"] is False
