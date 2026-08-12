"""CHANGE CHAIN ENGINE V1 — proposal engine orchestrator (no settlement)."""

from __future__ import annotations

from typing import Any

from .compatibility import get_compatibility
from .config import (
    CHANGE_CHAIN_MIN_LENGTH,
    CHAIN_ENGINE_VERSION,
    chain_max_length,
    change_chain_enabled,
)
from .cycles import ChainCycle, aggregate_chain_score, find_cycles
from .explain import explain_cycle
from .graph import build_edges, load_chain_nodes, prune_candidates_for_seed
from .pair_score import DeterministicScoreProvider
from .proposals import persist_proposal


class ChainEngineError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def ensure_chain_enabled() -> None:
    if not change_chain_enabled():
        raise ChainEngineError(
            "CHANGE_CHAIN_DISABLED",
            "Change Chain feature flag kapalı",
            501,
        )


def run_chain_match(
    conn,
    *,
    seed_listing_id: int,
    actor_id: int,
    max_length: int | None = None,
    max_results: int = 10,
    persist: bool = True,
    node_limit: int | None = None,
) -> dict[str, Any]:
    """
    Build on-demand graph → prune → detect cycles → optional proposal persist.
    Does NOT lock assets or transfer ownership.
    """
    ensure_chain_enabled()

    seed_row = conn.execute(
        "SELECT * FROM trade_listings WHERE id = ?", (seed_listing_id,)
    ).fetchone()
    if not seed_row:
        raise ChainEngineError("LISTING_NOT_FOUND", "Listing yok", 404)
    seed = dict(seed_row)
    for key in (
        "wanted_categories",
        "wanted_subcategories",
        "wanted_brands",
        "wanted_locations",
        "accept_categories",
        "attributes",
    ):
        from .. import db

        if isinstance(seed.get(key), str):
            seed[key] = db.loads(seed[key], [] if key != "attributes" else {})

    if int(seed["owner_id"]) != int(actor_id):
        raise ChainEngineError(
            "FORBIDDEN",
            "Yalnızca kendi listing'iniz için chain match başlatabilirsiniz",
            403,
        )

    from .matchability import is_chain_candidate

    if not is_chain_candidate(seed):
        raise ChainEngineError(
            "NOT_CHAIN_CANDIDATE",
            "Seed listing chain koşullarını karşılamıyor",
            409,
        )

    max_len = max_length if max_length is not None else chain_max_length()
    max_len = max(CHANGE_CHAIN_MIN_LENGTH, min(int(max_len), chain_max_length()))

    nodes = load_chain_nodes(conn, limit=node_limit)
    nodes = prune_candidates_for_seed(seed, nodes)
    # Ensure seed present
    if not any(int(n["id"]) == int(seed["id"]) for n in nodes):
        nodes.append(seed)

    scorer = DeterministicScoreProvider(get_compatibility())
    edges, adj = build_edges(nodes, scorer=scorer)
    nodes_by_id = {int(n["id"]): n for n in nodes}

    cycles = find_cycles(
        adj,
        nodes_by_id,
        seed_id=int(seed["id"]),
        min_length=CHANGE_CHAIN_MIN_LENGTH,
        max_length=max_len,
        max_cycles=max(1, int(max_results)),
    )

    # Enrich explanations
    for c in cycles:
        c.explanations = explain_cycle(c.edges, nodes_by_id)

    proposals: list[dict[str, Any]] = []
    if persist:
        for c in cycles:
            proposals.append(
                persist_proposal(conn, c, created_by=actor_id, nodes_by_id=nodes_by_id)
            )

    return {
        "engine_version": CHAIN_ENGINE_VERSION,
        "seed_listing_id": seed_listing_id,
        "candidate_node_count": len(nodes),
        "edge_count": len(edges),
        "cycle_count": len(cycles),
        "max_length": max_len,
        "cycles": [_cycle_public(c) for c in cycles],
        "proposals": proposals,
        "settlement": "NOT_IMPLEMENTED",
        "asset_lock": "NOT_IMPLEMENTED",
    }


def _cycle_public(c: ChainCycle) -> dict[str, Any]:
    return {
        "listing_ids": c.listing_ids,
        "owner_ids": c.owner_ids,
        "length": c.length,
        "edges": [e.to_dict() for e in c.edges],
        "explanations": c.explanations,
        "score": aggregate_chain_score(c),
    }


def benchmark_search(
    conn,
    *,
    seed_listing_id: int,
    actor_id: int,
    max_length: int | None = None,
) -> dict[str, Any]:
    """Match without persisting proposals — for benchmarks."""
    return run_chain_match(
        conn,
        seed_listing_id=seed_listing_id,
        actor_id=actor_id,
        max_length=max_length,
        persist=False,
        max_results=20,
    )
