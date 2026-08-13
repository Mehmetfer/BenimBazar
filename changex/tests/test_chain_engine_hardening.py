"""CHANGE X Chain Engine / Exchange Graph hardening — proposal ≠ settlement."""

from __future__ import annotations

import time

import pytest

from changex.app import db
from changex.app.matching import config as matching_config
from changex.app.matching.cycles import find_cycles
from changex.app.matching.edges import GraphEdge
from changex.app.matching.graph import build_edges
from changex.app.matching.integrity import (
    GraphIntegrityError,
    assert_graph_integrity,
    dedupe_edges,
    filter_valid_nodes,
    is_valid_node,
    revalidate_stored_edges,
)
from changex.app.matching.scoring import ScoreBreakdown
from changex.app.matching.settlement import (
    SETTLEMENT_STATUS,
    attempt_settlement,
    feature_disabled_payload,
    settlement_capability,
)
from changex.app.matching.asset_lock import reset_asset_lock_call_log, asset_lock_call_log
from changex.tests.helpers import auth, register
from changex.tests.test_chain_engine_v1 import _chain_listing, _triangle, _uid


@pytest.fixture()
def enable_chain(monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_ENABLED", True)
    reset_asset_lock_call_log()
    yield
    reset_asset_lock_call_log()


def _edge(src: int, tgt: int, so: int, to: int) -> GraphEdge:
    return GraphEdge(
        source_listing_id=src,
        target_listing_id=tgt,
        owner_id=so,
        target_owner_id=to,
        score=0.8,
        score_breakdown=ScoreBreakdown(category_score=1.0),
        reason="test",
    )


# ---- graph integrity ----


def test_invalid_nodes_filtered():
    ok, reasons = is_valid_node({"id": 0, "owner_id": 1, "category": "Spor"})
    assert not ok and "MISSING_ID" in reasons
    nodes, invalid = filter_valid_nodes(
        [
            {"id": 1, "owner_id": 1, "category": "Spor"},
            {"id": 2, "owner_id": 0, "category": "Ev"},
            {"id": 3, "owner_id": 3, "category": ""},
        ]
    )
    assert len(nodes) == 1
    assert len(invalid) == 2


def test_duplicate_edges_deduped_and_integrity():
    edges = [
        _edge(1, 2, 10, 20),
        _edge(1, 2, 10, 20),  # duplicate
        _edge(1, 1, 10, 10),  # self-loop
        _edge(2, 3, 20, 30),
    ]
    cleaned, dropped = dedupe_edges(edges)
    assert dropped == 2
    assert len(cleaned) == 2
    nodes = [
        {"id": 1, "owner_id": 10, "category": "A"},
        {"id": 2, "owner_id": 20, "category": "B"},
        {"id": 3, "owner_id": 30, "category": "C"},
    ]
    report = assert_graph_integrity(nodes, cleaned)
    assert report["ok"] is True


def test_integrity_rejects_same_owner_edge():
    nodes = [
        {"id": 1, "owner_id": 10, "category": "A"},
        {"id": 2, "owner_id": 10, "category": "B"},
    ]
    with pytest.raises(GraphIntegrityError) as ei:
        assert_graph_integrity(nodes, [_edge(1, 2, 10, 10)])
    assert ei.value.code == "GRAPH_INTEGRITY_VIOLATION"


def test_build_edges_no_duplicates(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    with db.connect() as conn:
        from changex.app.matching.graph import load_chain_nodes

        nodes = load_chain_nodes(conn)
        edges, adj = build_edges(nodes)
        pairs = [(e.source_listing_id, e.target_listing_id) for e in edges]
        assert len(pairs) == len(set(pairs))
        for e in edges:
            assert e.source_listing_id != e.target_listing_id


# ---- proposal vs settlement boundary ----


def test_settlement_capability_is_not_implemented():
    cap = settlement_capability()
    assert cap["settlement"] == "NOT_IMPLEMENTED"
    assert cap["asset_lock"] == "NOT_IMPLEMENTED"
    assert cap["engine_phase"] == "PROPOSAL_ONLY"
    assert cap["ownership_transferred"] is False
    assert cap["settlement_available"] is False
    assert "NOT_IMPLEMENTED" in cap["user_message"]


def test_attempt_settlement_never_transfers():
    result = attempt_settlement("chain-x", [1, 2, 3])
    assert result["code"] == "NOT_IMPLEMENTED"
    assert result["settlement"] == SETTLEMENT_STATUS
    assert result["ownership_transferred"] is False
    assert asset_lock_call_log()  # guarded call recorded


def test_match_response_marks_settlement_not_implemented(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["settlement"] == "NOT_IMPLEMENTED"
    assert body["asset_lock"] == "NOT_IMPLEMENTED"
    assert body["engine_phase"] == "PROPOSAL_ONLY"
    assert body["consent_only"] is True
    assert body["ownership_transferred"] is False
    assert body["graph_integrity"]["ok"] is True
    assert body["proposals"][0]["settlement"] == "NOT_IMPLEMENTED"


def test_settle_endpoint_explicit_not_implemented(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    for u in (ua, ub, uc):
        assert (
            client.post(
                f"/api/change-chain/proposals/{prop['id']}/accept",
                headers=auth(u["token"]),
                json={},
            ).status_code
            == 200
        )
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/settle",
        headers=auth(ua["token"]),
    )
    assert r.status_code == 501
    detail = r.json()["detail"]
    assert detail["code"] == "NOT_IMPLEMENTED"
    assert detail["settlement"] == "NOT_IMPLEMENTED"
    assert detail["asset_lock"] == "NOT_IMPLEMENTED"
    assert detail["ownership_transferred"] is False


def test_accepted_is_consent_not_settlement(client, enable_chain):
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
    detail = client.get(
        f"/api/change-chain/proposals/{prop['id']}",
        headers=auth(ua["token"]),
    ).json()
    assert detail["status"] == "ACCEPTED"
    assert detail["engine_phase"] == "PROPOSAL_ONLY"
    assert detail["settlement"] == "NOT_IMPLEMENTED"
    assert detail["consent_only"] is True
    with db.connect() as conn:
        for lid in detail["listing_ids"]:
            row = conn.execute(
                "SELECT inventory_status, owner_id FROM trade_listings WHERE id=?",
                (lid,),
            ).fetchone()
            assert row["inventory_status"] == "AVAILABLE"


# ---- feature flag OFF clarity ----


def test_feature_flag_off_user_message(client, monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_ENABLED", False)
    u = register(client, f"hard_flag_{time.time_ns()}")
    r = client.post(
        "/api/change-chain/match",
        headers=auth(u["token"]),
        json={"listing_id": 1},
    )
    assert r.status_code == 501
    detail = r.json()["detail"]
    assert detail["code"] == "CHANGE_CHAIN_DISABLED"
    assert "user_message" in detail
    assert "NOT_IMPLEMENTED" in detail["user_message"]
    assert detail["settlement"] == "NOT_IMPLEMENTED"


def test_change_chain_status_when_disabled(client, monkeypatch):
    monkeypatch.setattr(matching_config, "CHANGE_CHAIN_ENABLED", False)
    r = client.get("/api/change-chain/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["settlement"] == "NOT_IMPLEMENTED"
    assert "kapalı" in body["user_message"].lower() or "kapali" in body["user_message"].lower()


def test_preferences_include_settlement_boundary(client):
    u = register(client, f"hard_pref_{time.time_ns()}")
    r = client.get("/api/matching/preferences", headers=auth(u["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["feature_flags"]["CHANGE_CHAIN_ENABLED"] is False
    assert body["settlement"] == "NOT_IMPLEMENTED"
    assert body["user_message"]


def test_disabled_payload_helper():
    p = feature_disabled_payload()
    assert p["code"] == "CHANGE_CHAIN_DISABLED"
    assert p["asset_lock"] == "NOT_IMPLEMENTED"


# ---- stale edges ----


def test_stale_edge_invalidates_accept(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    prop = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()["proposals"][0]
    # Break WANT compatibility while keeping APPROVED+AVAILABLE+chain candidate
    with db.connect() as conn:
        conn.execute(
            "UPDATE trade_listings SET wanted_categories = ? WHERE id = ?",
            (db.dumps(["Kitap"]), a["id"]),
        )
        conn.commit()
    r = client.post(
        f"/api/change-chain/proposals/{prop['id']}/accept",
        headers=auth(ua["token"]),
        json={},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "STALE_EDGE"


def test_revalidate_stored_edges_unit(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    with db.connect() as conn:
        edges = [
            {
                "source_listing_id": a["id"],
                "target_listing_id": b["id"],
            }
        ]
        revalidate_stored_edges(conn, edges)  # still valid
        conn.execute(
            "UPDATE trade_listings SET wanted_categories = ? WHERE id = ?",
            (db.dumps(["Kitap"]), a["id"]),
        )
        with pytest.raises(GraphIntegrityError) as ei:
            revalidate_stored_edges(conn, edges)
        assert ei.value.code == "STALE_EDGE"


# ---- concurrency / dedupe ----


def test_rematch_reuses_open_proposal(client, enable_chain):
    ua, ub, uc, a, b, c = _triangle(client)
    r1 = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()
    r2 = client.post(
        "/api/change-chain/match",
        headers=auth(ua["token"]),
        json={"listing_id": a["id"]},
    ).json()
    assert r1["proposals"][0]["id"] == r2["proposals"][0]["id"]
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM chain_proposals").fetchone()["c"]
        assert int(n) == 1


def test_cycle_detection_still_rejects_two_node():
    adj = {
        1: [_edge(1, 2, 10, 20)],
        2: [_edge(2, 1, 20, 10)],
    }
    nodes = {
        1: {"id": 1, "owner_id": 10},
        2: {"id": 2, "owner_id": 20},
    }
    cycles = find_cycles(adj, nodes, seed_id=1, min_length=3, max_length=4)
    assert cycles == []
