"""CHANGE X Chain Engine V1 — proposal engine tests (no settlement)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from changex.app import db
from changex.app.domain_status import InventoryStatus, ModerationStatus
from changex.app.matching import config as matching_config
from changex.app.matching.asset_lock import (
    AssetLockError,
    get_asset_lock_provider,
    reset_asset_lock_call_log,
    asset_lock_call_log,
    guarded_asset_lock_call,
)
from changex.app.matching.cycles import find_cycles
from changex.app.matching.edges import GraphEdge
from changex.app.matching.graph import build_edges
from changex.app.matching.pair_score import DeterministicScoreProvider, can_form_edge
from changex.app.matching.scoring import ScoreBreakdown
from changex.app.value import MANDAL_PER_MADALYON
from changex.tests.helpers import approve_listing, auth, make_listing, register


@pytest.fixture()
def enable_chain(monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_ENABLED", True)
    reset_asset_lock_call_log()
    yield
    reset_asset_lock_call_log()


def _chain_listing(
    client,
    token: str,
    title: str,
    *,
    category: str,
    want_categories: list[str],
    brand: str = "",
    madalyon: int = 1,
    wanted_brands: list[str] | None = None,
    wanted_value_min: dict | None = None,
    wanted_value_max: dict | None = None,
    value_gap_tolerance: int = 0,
    chain_opt_in: bool = True,
    trade_preference: str = "CHAIN_ALLOWED",
    wanted_items: str = "",
    approve: bool = True,
):
    payload = {
        "title": title,
        "description": title,
        "category": category,
        "brand": brand,
        "wanted_categories": want_categories,
        "wanted_brands": wanted_brands or [],
        "wanted_items": wanted_items,
        "chain_opt_in": chain_opt_in,
        "trade_preference": trade_preference,
        "value_gap_tolerance": value_gap_tolerance,
        "items": [{"name": title, "value": {"madalyon": madalyon, "dirhem": 0, "mandal": 0}}],
    }
    if wanted_value_min is not None:
        payload["wanted_value_min"] = wanted_value_min
    if wanted_value_max is not None:
        payload["wanted_value_max"] = wanted_value_max
    r = client.post("/api/listings", headers=auth(token), json=payload)
    assert r.status_code == 200, r.text
    listing = r.json()
    if approve:
        listing = approve_listing(client, listing["id"])
    return listing


def _set_inventory(listing_id: int, inv: str, *, legacy: str | None = None) -> None:
    with db.connect() as conn:
        db.sync_dual_status(
            conn,
            listing_id,
            inventory_status=inv,
            moderation_status=ModerationStatus.APPROVED.value
            if inv != "CANCELLED"
            else ModerationStatus.REJECTED.value,
            legacy_status=legacy or inv,
        )


def _set_moderation(listing_id: int, mod: str) -> None:
    with db.connect() as conn:
        db.sync_dual_status(
            conn,
            listing_id,
            moderation_status=mod,
            inventory_status=InventoryStatus.AVAILABLE.value,
            legacy_status=mod,
        )


def _owners_snapshot(listing_ids: list[int]) -> dict[int, int]:
    with db.connect() as conn:
        out = {}
        for lid in listing_ids:
            row = conn.execute(
                "SELECT owner_id FROM trade_listings WHERE id = ?", (lid,)
            ).fetchone()
            out[lid] = int(row["owner_id"])
        return out


def _uid(user: dict) -> int:
    return int(user["user"]["id"])


def _triangle(client):
    """A(Otomobil→Telefon) → B(Telefon→Spor) → C(Spor→Otomobil) → A"""
    ua = register(client, f"ch_a_{time.time_ns()}")
    ub = register(client, f"ch_b_{time.time_ns()}")
    uc = register(client, f"ch_c_{time.time_ns()}")
    a = _chain_listing(
        client, ua["token"], "BMW", category="Otomobil", want_categories=["Telefon"], brand="BMW"
    )
    b = _chain_listing(
        client, ub["token"], "iPhone", category="Telefon", want_categories=["Spor"], brand="Apple"
    )
    c = _chain_listing(
        client, uc["token"], "Motorcycle", category="Spor", want_categories=["Otomobil"], brand="Yamaha"
    )
    return ua, ub, uc, a, b, c


# ---- unit gates ----


def test_self_loop_rejected():
    node = {
        "id": 1,
        "owner_id": 1,
        "category": "Telefon",
        "wanted_categories": ["Telefon"],
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    ok, reasons = can_form_edge(node, node)
    assert not ok
    assert "SELF_LOOP" in reasons


def test_two_node_cycle_rejected():
    a = {
        "id": 1,
        "owner_id": 10,
        "category": "Otomobil",
        "wanted_categories": ["Telefon"],
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    b = {
        "id": 2,
        "owner_id": 20,
        "category": "Telefon",
        "wanted_categories": ["Otomobil"],
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    edges, adj = build_edges([a, b])
    assert len(edges) == 2
    cycles = find_cycles(adj, {1: a, 2: b}, seed_id=1, min_length=3, max_length=4)
    assert cycles == []


def test_three_node_cycle_detected(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"], "max_length": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cycle_count"] >= 1
    lengths = {cy["length"] for cy in body["cycles"]}
    assert 3 in lengths
    ids = set(body["cycles"][0]["listing_ids"])
    assert ids == {a["id"], b["id"], c["id"]}


def test_four_node_cycle_detected(client, enable_chain):
    u1 = register(client, f"ch4_1_{time.time_ns()}")
    u2 = register(client, f"ch4_2_{time.time_ns()}")
    u3 = register(client, f"ch4_3_{time.time_ns()}")
    u4 = register(client, f"ch4_4_{time.time_ns()}")
    a = _chain_listing(client, u1["token"], "CarA", category="Otomobil", want_categories=["Telefon"])
    b = _chain_listing(client, u2["token"], "PhoneB", category="Telefon", want_categories=["Spor"])
    c = _chain_listing(client, u3["token"], "BikeC", category="Spor", want_categories=["Kitap"])
    d = _chain_listing(client, u4["token"], "BookD", category="Kitap", want_categories=["Otomobil"])
    r = client.post(
        "/api/change-chain/match",
        headers=auth(u1["token"]),
        json={"listing_id": a["id"], "max_length": 4},
    )
    assert r.status_code == 200, r.text
    assert any(cy["length"] == 4 for cy in r.json()["cycles"])
    assert {a["id"], b["id"], c["id"], d["id"]} == set(
        next(cy["listing_ids"] for cy in r.json()["cycles"] if cy["length"] == 4)
    )


def test_max_chain_length_enforced(client, enable_chain, monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_MAX_LENGTH", 3)
    u1 = register(client, f"chmax_1_{time.time_ns()}")
    u2 = register(client, f"chmax_2_{time.time_ns()}")
    u3 = register(client, f"chmax_3_{time.time_ns()}")
    u4 = register(client, f"chmax_4_{time.time_ns()}")
    a = _chain_listing(client, u1["token"], "CarA", category="Otomobil", want_categories=["Telefon"])
    _chain_listing(client, u2["token"], "PhoneB", category="Telefon", want_categories=["Spor"])
    _chain_listing(client, u3["token"], "BikeC", category="Spor", want_categories=["Kitap"])
    _chain_listing(client, u4["token"], "BookD", category="Kitap", want_categories=["Otomobil"])
    r = client.post(
        "/api/change-chain/match",
        headers=auth(u1["token"]),
        json={"listing_id": a["id"], "max_length": 3},
    )
    assert r.status_code == 200
    assert all(cy["length"] <= 3 for cy in r.json()["cycles"])
    assert not any(cy["length"] == 4 for cy in r.json()["cycles"])


def test_same_owner_duplication_rejected(client, enable_chain):
    ua = register(client, f"ch_own_{time.time_ns()}")
    ub = register(client, f"ch_ownb_{time.time_ns()}")
    # Same owner holds A and C — would be A→B→C→A with owners A,B,A
    a = _chain_listing(client, ua["token"], "BMW", category="Otomobil", want_categories=["Telefon"])
    b = _chain_listing(client, ub["token"], "iPhone", category="Telefon", want_categories=["Spor"])
    c = _chain_listing(client, ua["token"], "Bike", category="Spor", want_categories=["Otomobil"])
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert len(cy["owner_ids"]) == len(set(cy["owner_ids"]))
        assert set(cy["listing_ids"]) != {a["id"], b["id"], c["id"]}


def test_unapproved_listing_excluded(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    pending = _chain_listing(
        client,
        register(client, f"pend_{time.time_ns()}")["token"],
        "Pend",
        category="Elektronik",
        want_categories=["Otomobil"],
        approve=False,
    )
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert pending["id"] not in cy["listing_ids"]


@pytest.mark.parametrize(
    "inv",
    ["RESERVED", "TRADED", "CANCELLED", "EXPIRED"],
)
def test_blocked_inventory_excluded(client, enable_chain, inv):
    ua, ub, uc, a, b, c = _triangle(client)
    _set_inventory(b["id"], inv)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert b["id"] not in cy["listing_ids"]


def test_suspended_listing_excluded(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    _set_moderation(b["id"], ModerationStatus.SUSPENDED.value)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert b["id"] not in cy["listing_ids"]


def test_chain_opt_in_false_excluded(client, enable_chain):
    ua = register(client, f"optf_a_{time.time_ns()}")
    ub = register(client, f"optf_b_{time.time_ns()}")
    uc = register(client, f"optf_c_{time.time_ns()}")
    a = _chain_listing(client, ua["token"], "CarA", category="Otomobil", want_categories=["Telefon"])
    b = _chain_listing(
        client,
        ub["token"],
        "PhoneB",
        category="Telefon",
        want_categories=["Spor"],
        chain_opt_in=False,
        trade_preference="CHAIN_ALLOWED",
    )
    _chain_listing(client, uc["token"], "BikeC", category="Spor", want_categories=["Otomobil"])
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert b["id"] not in cy["listing_ids"]


def test_direct_only_excluded(client, enable_chain):
    ua = register(client, f"dir_a_{time.time_ns()}")
    ub = register(client, f"dir_b_{time.time_ns()}")
    uc = register(client, f"dir_c_{time.time_ns()}")
    a = _chain_listing(client, ua["token"], "CarA", category="Otomobil", want_categories=["Telefon"])
    b = _chain_listing(
        client,
        ub["token"],
        "PhoneB",
        category="Telefon",
        want_categories=["Spor"],
        trade_preference="DIRECT_ONLY",
    )
    _chain_listing(client, uc["token"], "BikeC", category="Spor", want_categories=["Otomobil"])
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    for cy in r.json()["cycles"]:
        assert b["id"] not in cy["listing_ids"]


def test_structured_want_match(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    assert r.json()["cycle_count"] >= 1
    edge = r.json()["cycles"][0]["edges"][0]
    assert edge["score_breakdown"]["want_score"] > 0
    assert edge["score_breakdown"]["category_score"] > 0


def test_incompatible_category_rejected(client, enable_chain):
    ua = register(client, f"inc_a_{time.time_ns()}")
    ub = register(client, f"inc_b_{time.time_ns()}")
    a = _chain_listing(
        client, ua["token"], "WantBMW", category="Telefon", want_categories=["Otomobil"], wanted_brands=["BMW"]
    )
    b = _chain_listing(
        client, ub["token"], "Phone", category="Telefon", want_categories=["Telefon"], brand="Apple"
    )
    ok, reasons = can_form_edge(
        {
            "id": a["id"],
            "owner_id": _uid(ua),
            "category": "Telefon",
            "wanted_categories": ["Otomobil"],
            "wanted_brands": ["BMW"],
            "mandal_units": MANDAL_PER_MADALYON,
            "trade_preference": "CHAIN_ALLOWED",
        },
        {
            "id": b["id"],
            "owner_id": _uid(ub),
            "category": "Telefon",
            "title": "Phone",
            "brand": "Apple",
            "mandal_units": MANDAL_PER_MADALYON,
            "trade_preference": "CHAIN_ALLOWED",
        },
    )
    assert not ok
    assert "CATEGORY_INCOMPATIBLE" in reasons


def test_value_tolerance_respected(client, enable_chain):
    src = {
        "id": 1,
        "owner_id": 1,
        "category": "Otomobil",
        "wanted_categories": ["Telefon"],
        "wanted_value_min": 1000,
        "wanted_value_max": 2000,
        "value_gap_tolerance": 100,
        "mandal_units": 5000,
        "trade_preference": "CHAIN_ALLOWED",
    }
    far = {
        "id": 2,
        "owner_id": 2,
        "category": "Telefon",
        "mandal_units": 5000,
        "trade_preference": "CHAIN_ALLOWED",
    }
    near = {
        "id": 3,
        "owner_id": 3,
        "category": "Telefon",
        "mandal_units": 1950,
        "trade_preference": "CHAIN_ALLOWED",
    }
    ok_far, reasons = can_form_edge(src, far)
    ok_near, _ = can_form_edge(src, near)
    assert not ok_far
    assert "VALUE_OUT_OF_TOLERANCE" in reasons
    assert ok_near


def test_free_text_fallback_does_not_override_gates():
    src = {
        "id": 1,
        "owner_id": 1,
        "category": "Otomobil",
        "wanted_categories": [],
        "wanted_items": "BMW X5",
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    tgt = {
        "id": 2,
        "owner_id": 2,
        "category": "Telefon",
        "title": "telefon",
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    ok, reasons = can_form_edge(src, tgt)
    assert not ok
    assert "FREE_TEXT_ONLY_INSUFFICIENT" in reasons


def test_proposal_created_and_participants(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    assert r.json()["proposals"]
    prop = r.json()["proposals"][0]
    assert prop["status"] == "PROPOSED"
    assert set(prop["owner_ids"]) == {_uid(ua), _uid(ub), _uid(uc)}
    assert len(prop["participants"]) == 3
    assert all(p["consent"] == "PENDING" for p in prop["participants"])


def test_all_party_consent_and_no_partial_settle(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    prop = r.json()["proposals"][0]
    owners_before = _owners_snapshot(prop["listing_ids"])
    r1 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "PARTIALLY_ACCEPTED"
    assert r1.json()["ownership_transferred"] is False
    r2 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ub["token"]),
        json={},
    )
    assert r2.json()["status"] == "PARTIALLY_ACCEPTED"
    r3 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(uc["token"]),
        json={},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "ACCEPTED"
    assert r3.json()["settlement"] == "NOT_IMPLEMENTED"
    assert r3.json()["ownership_transferred"] is False
    assert _owners_snapshot(prop["listing_ids"]) == owners_before


def test_reject_cancels_proposal(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/reject",
        headers=auth(ub["token"]),
        json={},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"


def test_expiration_prevents_acceptance(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    with db.connect() as conn:
        conn.execute(
            "UPDATE chain_proposals SET expires_at = ? WHERE id = ?",
            (time.time() - 10, prop["id"]),
        )
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CHAIN_EXPIRED"


def test_stale_listing_invalidates_proposal(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    _set_inventory(b["id"], "RESERVED", legacy="RESERVED")
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] in {"STALE_LISTING", "MODERATION_INVALID"}


def test_moderation_revision_invalidates_proposal(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    _set_moderation(c["id"], ModerationStatus.EDIT_REQUIRED.value)
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MODERATION_INVALID"


def test_concurrent_accept_protected(client, enable_chain, tmp_db):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    # First accept by A
    assert (
        client.post(
            f"/api/change-chain/proposals/{prop['id']}/accept",
            headers=auth(ua["token"]),
            json={},
        ).status_code
        == 200
    )

    results: list[int] = []
    barrier = threading.Barrier(2)

    def _accept(token: str):
        barrier.wait()
        rr = client.post(
            f"/api/change-chain/proposals/{prop['id']}/accept",
            headers=auth(token),
            json={"expected_version": 1},  # stale version after A's accept
        )
        results.append(rr.status_code)

    t1 = threading.Thread(target=_accept, args=(ub["token"],))
    t2 = threading.Thread(target=_accept, args=(uc["token"],))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # At least one should see conflict due to expected_version, or both succeed without version
    # Using expected_version=1 after A bumped version → both 409
    assert all(code in {200, 409} for code in results)
    assert 409 in results


def test_idempotent_accept(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    key = f"idem-acc-{time.time_ns()}"
    r1 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={"idempotency_key": key},
    )
    r2 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={"idempotency_key": key},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == r2.json()["status"]
    with db.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM chain_proposal_participants WHERE proposal_id=? AND owner_id=? AND consent='ACCEPTED'",
            (prop["id"], _uid(ua)),
        ).fetchone()["c"]
    assert n == 1


def test_idempotent_reject(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    key = f"idem-rej-{time.time_ns()}"
    r1 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/reject",
        headers=auth(ub["token"]),
        json={"idempotency_key": key},
    )
    r2 = client.post(
        f"/api/change-chain/proposals/{prop['id']}/reject",
        headers=auth(ub["token"]),
        json={"idempotency_key": key},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == "REJECTED"
    assert r2.json()["status"] == "REJECTED"


def test_unauthorized_participant_action_rejected(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    stranger = register(client, f"stranger_{time.time_ns()}")
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(stranger["token"]),
        json={},
    )
    assert r.status_code == 403


def test_feature_flag_disabled(client, monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_ENABLED", False)
    u = register(client, f"flag_off_{time.time_ns()}")
    a = make_listing(client, u["token"], "XX")
    b = make_listing(client, u["token"], "YY")
    r = client.post(
        "/api/change-chain/match",
        headers=auth(u["token"]),
        json={"requested_listing_ids": [a["id"]], "offered_listing_ids": [b["id"]]},
    )
    assert r.status_code == 501
    assert r.json()["detail"]["code"] == "CHANGE_CHAIN_DISABLED"


def test_feature_flag_enabled(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    assert r.json()["engine_version"] == "CHANGE_CHAIN_ENGINE_V1"


def test_explainability_data_generated(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    prop = r.json()["proposals"][0]
    assert prop["explanations"]
    assert len(prop["explanations"]) == prop["length"]
    assert all(isinstance(x, str) and len(x) > 10 for x in prop["explanations"])


def test_score_breakdown_deterministic():
    scorer = DeterministicScoreProvider()
    src = {
        "id": 1,
        "owner_id": 1,
        "category": "Otomobil",
        "wanted_categories": ["Telefon"],
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    tgt = {
        "id": 2,
        "owner_id": 2,
        "category": "Telefon",
        "title": "Phone",
        "condition": "good",
        "mandal_units": 100,
        "trade_preference": "CHAIN_ALLOWED",
    }
    s1 = scorer.score_pair(src, tgt)
    s2 = scorer.score_pair(src, tgt)
    assert s1.to_dict() == s2.to_dict()
    assert isinstance(s1, ScoreBreakdown)
    assert s1.total_score == s2.total_score


def test_asset_ownership_unchanged(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    before = _owners_snapshot(prop["listing_ids"])
    for u in (ua, ub, uc):
        client.post(
            f"/api/change-chain/proposals/{prop['id']}/accept",
            headers=auth(u["token"]),
            json={},
        )
    assert _owners_snapshot(prop["listing_ids"]) == before


def test_asset_lock_not_implemented_and_not_called(client, enable_chain):
    reset_asset_lock_call_log()
    provider = get_asset_lock_provider()
    with pytest.raises(AssetLockError) as ei:
        provider.lock("x", [1, 2, 3])
    assert ei.value.code == "ASSET_LOCK_NOT_IMPLEMENTED"
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    for u in (ua, ub, uc):
        client.post(
            f"/api/change-chain/proposals/{prop['id']}/accept",
            headers=auth(u["token"]),
            json={},
        )
    assert asset_lock_call_log() == []
    with pytest.raises(AssetLockError):
        guarded_asset_lock_call("commit", prop["chain_id"])


def test_proposals_list_and_detail(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    lst = client.get("/api/change-chain/proposals", headers=auth(ub["token"]))
    assert lst.status_code == 200
    assert any(p["id"] == prop["id"] for p in lst.json()["proposals"])
    detail = client.get(f"/api/change-chain/proposals/{prop['id']}", headers=auth(uc["token"]))
    assert detail.status_code == 200
    assert detail.json()["chain_id"] == prop["chain_id"]
