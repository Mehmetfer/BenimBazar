"""On-demand exchange graph: load eligible nodes, prune, build edges."""

from __future__ import annotations

from typing import Any

from .. import db
from ..domain_status import InventoryStatus, ModerationStatus, TradePreference
from .compatibility import CategoryCompatibility, get_compatibility
from .edges import GraphEdge
from .integrity import (
    assert_graph_integrity,
    dedupe_edges,
    filter_valid_nodes,
    rebuild_adjacency,
)
from .matchability import is_chain_candidate
from .pair_score import DeterministicScoreProvider, can_form_edge
from .preferences import get_user_preferences


def _parse_listing(row: Any) -> dict[str, Any]:
    d = dict(row)
    for key in (
        "wanted_categories",
        "wanted_subcategories",
        "wanted_brands",
        "wanted_locations",
        "accept_categories",
        "attributes",
    ):
        if isinstance(d.get(key), str):
            d[key] = db.loads(d[key], [] if key != "attributes" else {})
    return d


def load_chain_nodes(conn, *, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Backend-enforced node gates:
    APPROVED, AVAILABLE, chain_opt_in, CHAIN_ALLOWED,
    owner active, not suspended/expired/cancelled/traded/reserved.
    """
    sql = """
        SELECT l.*, u.suspended AS owner_suspended, u.role AS owner_role
        FROM trade_listings l
        JOIN users u ON u.id = l.owner_id
        WHERE COALESCE(l.moderation_status, '') = ?
          AND COALESCE(l.inventory_status, '') = ?
          AND COALESCE(l.chain_opt_in, 0) = 1
          AND COALESCE(l.trade_preference, 'DIRECT_ONLY') = ?
          AND COALESCE(u.suspended, 0) = 0
          AND COALESCE(l.status, '') NOT IN (
            'RESERVED','TRADED','CANCELLED','EXPIRED','SUSPENDED','REJECTED'
          )
    """
    params: list[Any] = [
        ModerationStatus.APPROVED.value,
        InventoryStatus.AVAILABLE.value,
        TradePreference.CHAIN_ALLOWED.value,
    ]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    nodes: list[dict[str, Any]] = []
    for row in rows:
        d = _parse_listing(row)
        prefs = get_user_preferences(conn, int(d["owner_id"]))
        # Listing-level preference already CHAIN_ALLOWED; user pref may still be DIRECT_ONLY —
        # require listing.chain_opt_in (already filtered) and listing trade_preference.
        if not is_chain_candidate(d, user_pref=d.get("trade_preference")):
            continue
        if int(d.get("owner_suspended") or 0):
            continue
        # Soft: if user prefs explicitly DIRECT_ONLY and listing somehow mismatched — skip
        if prefs.get("trade_preference") == TradePreference.DIRECT_ONLY.value and not bool(
            prefs.get("chain_opt_in")
        ):
            # Listing can still opt in independently; do not block if listing opted in
            pass
        nodes.append(d)
    valid, _invalid = filter_valid_nodes(nodes)
    return valid


def prune_candidates_for_seed(
    seed: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    compat: CategoryCompatibility | None = None,
) -> list[dict[str, Any]]:
    """Narrow nodes that could participate in a cycle with seed (category/value prune)."""
    compat = compat or get_compatibility()
    seed_id = int(seed["id"])
    seed_owner = int(seed["owner_id"])
    seed_have = str(seed.get("category") or "")
    seed_want = seed.get("wanted_categories") or seed.get("accept_categories") or []
    if isinstance(seed_want, str):
        seed_want = db.loads(seed_want, [])

    out: list[dict[str, Any]] = []
    for n in nodes:
        if int(n["id"]) == seed_id:
            out.append(n)
            continue
        if int(n["owner_id"]) == seed_owner:
            continue
        # Keep if: seed wants n's have OR n wants seed's have OR n could bridge categories
        n_have = str(n.get("category") or "")
        n_want = n.get("wanted_categories") or n.get("accept_categories") or []
        if isinstance(n_want, str):
            n_want = db.loads(n_want, [])
        seed_wants_n = any(compat.compatible(n_have, w) for w in seed_want) if seed_want else False
        n_wants_seed = any(compat.compatible(seed_have, w) for w in n_want) if n_want else False
        # Bridge: keep nodes with structured want (potential middle of chain)
        if seed_wants_n or n_wants_seed or n_want:
            out.append(n)
    return out


def build_edges(
    nodes: list[dict[str, Any]],
    *,
    scorer: DeterministicScoreProvider | None = None,
    compat: CategoryCompatibility | None = None,
    enforce_integrity: bool = True,
) -> tuple[list[GraphEdge], dict[int, list[GraphEdge]]]:
    """On-demand candidate generation with category-index pruning (not full n²)."""
    scorer = scorer or DeterministicScoreProvider(compat)
    compat = compat or get_compatibility()
    nodes, _invalid = filter_valid_nodes(nodes)
    edges: list[GraphEdge] = []

    # Index HAVE listings by lowercased category for pruning
    by_category: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        cat = str(n.get("category") or "").strip().lower()
        by_category.setdefault(cat, []).append(n)

    for src in nodes:
        want_cats = src.get("wanted_categories") or src.get("accept_categories") or []
        if isinstance(want_cats, str):
            want_cats = db.loads(want_cats, [])
        if not want_cats:
            continue
        # Candidate targets: listings whose HAVE category is compatible with any WANT
        candidates: list[dict[str, Any]] = []
        seen: set[int] = set()
        for w in want_cats:
            key = str(w).strip().lower()
            # Fast path: same-category bucket
            for tgt in by_category.get(key, []):
                tid = int(tgt["id"])
                if tid not in seen:
                    seen.add(tid)
                    candidates.append(tgt)
            # Extended matrix edges (admin-configured cross-category)
            for cat_key, group in by_category.items():
                if cat_key == key:
                    continue
                if not compat.compatible(cat_key, key):
                    continue
                for tgt in group:
                    tid = int(tgt["id"])
                    if tid in seen:
                        continue
                    seen.add(tid)
                    candidates.append(tgt)
        for tgt in candidates:
            if int(src["id"]) == int(tgt["id"]):
                continue
            ok, _reasons = can_form_edge(src, tgt, compat=compat)
            if not ok:
                continue
            breakdown = scorer.score_pair(src, tgt)
            reason = _edge_reason(src, tgt)
            edge = GraphEdge(
                source_listing_id=int(src["id"]),
                target_listing_id=int(tgt["id"]),
                owner_id=int(src["owner_id"]),
                target_owner_id=int(tgt["owner_id"]),
                score=breakdown.total_score,
                score_breakdown=breakdown,
                reason=reason,
            )
            edges.append(edge)

    edges, _dropped = dedupe_edges(edges)
    adj = rebuild_adjacency(edges, [int(n["id"]) for n in nodes])
    if enforce_integrity:
        assert_graph_integrity(nodes, edges)
    return edges, adj


def _edge_reason(src: dict[str, Any], tgt: dict[str, Any]) -> str:
    have = str(tgt.get("title") or tgt.get("brand") or tgt.get("category") or "ürün")
    want_cats = src.get("wanted_categories") or []
    if isinstance(want_cats, str):
        want_cats = db.loads(want_cats, [])
    cat = want_cats[0] if want_cats else str(tgt.get("category") or "")
    return (
        f"{have}, listing #{src.get('id')} sahibinin istediği "
        f"{cat or 'kriter'} ile uyumlu (HAVE→WANT)."
    )
