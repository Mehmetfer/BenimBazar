"""Exchange graph integrity checks — nodes, edges, cycles (no settlement)."""

from __future__ import annotations

from typing import Any

from .edges import GraphEdge
from .pair_score import can_form_edge


class GraphIntegrityError(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def is_valid_node(node: dict[str, Any]) -> tuple[bool, list[str]]:
    """Reject structurally invalid listing nodes before edge build."""
    reasons: list[str] = []
    if not int(node.get("id") or 0):
        reasons.append("MISSING_ID")
    if not int(node.get("owner_id") or 0):
        reasons.append("MISSING_OWNER")
    if not str(node.get("category") or "").strip():
        reasons.append("MISSING_CATEGORY")
    return (not reasons), reasons


def filter_valid_nodes(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for n in nodes:
        ok, reasons = is_valid_node(n)
        if ok:
            valid.append(n)
        else:
            invalid.append({"id": n.get("id"), "reasons": reasons})
    return valid, invalid


def dedupe_edges(edges: list[GraphEdge]) -> tuple[list[GraphEdge], int]:
    """Keep first edge per (source, target); drop self-loops and duplicate pairs."""
    seen: set[tuple[int, int]] = set()
    out: list[GraphEdge] = []
    dropped = 0
    for e in edges:
        if e.source_listing_id == e.target_listing_id:
            dropped += 1
            continue
        key = (e.source_listing_id, e.target_listing_id)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(e)
    return out, dropped


def rebuild_adjacency(edges: list[GraphEdge], node_ids: list[int]) -> dict[int, list[GraphEdge]]:
    adj: dict[int, list[GraphEdge]] = {nid: [] for nid in node_ids}
    for e in edges:
        if e.source_listing_id in adj:
            adj[e.source_listing_id].append(e)
    return adj


def assert_graph_integrity(
    nodes: list[dict[str, Any]],
    edges: list[GraphEdge],
) -> dict[str, Any]:
    """
    Soft-validate graph after build. Raises only on hard corruption
    (edge endpoints missing from node set). Duplicate/self-loop should already
    be stripped by dedupe_edges.
    """
    by_id = {int(n["id"]): n for n in nodes if int(n.get("id") or 0)}
    pair_seen: set[tuple[int, int]] = set()
    issues: list[str] = []
    for e in edges:
        if e.source_listing_id not in by_id or e.target_listing_id not in by_id:
            raise GraphIntegrityError(
                "INVALID_EDGE_ENDPOINT",
                "Edge references missing node",
                details={
                    "source": e.source_listing_id,
                    "target": e.target_listing_id,
                },
            )
        src = by_id[e.source_listing_id]
        tgt = by_id[e.target_listing_id]
        if int(e.owner_id) != int(src["owner_id"]):
            issues.append(f"OWNER_MISMATCH_SRC:{e.source_listing_id}")
        if int(e.target_owner_id) != int(tgt["owner_id"]):
            issues.append(f"OWNER_MISMATCH_TGT:{e.target_listing_id}")
        if e.source_listing_id == e.target_listing_id:
            issues.append(f"SELF_LOOP:{e.source_listing_id}")
        key = (e.source_listing_id, e.target_listing_id)
        if key in pair_seen:
            issues.append(f"DUPLICATE_EDGE:{key[0]}->{key[1]}")
        pair_seen.add(key)
        if int(src["owner_id"]) == int(tgt["owner_id"]):
            issues.append(f"SAME_OWNER_EDGE:{key[0]}->{key[1]}")

    hard = [i for i in issues if i.startswith(("SELF_LOOP", "DUPLICATE_EDGE", "SAME_OWNER_EDGE"))]
    if hard:
        raise GraphIntegrityError(
            "GRAPH_INTEGRITY_VIOLATION",
            "Graph failed integrity checks",
            details={"issues": hard},
        )
    return {
        "ok": True,
        "node_count": len(by_id),
        "edge_count": len(edges),
        "warnings": issues,
    }


def revalidate_stored_edges(
    conn,
    edges_payload: list[dict[str, Any]],
    *,
    listing_rows: dict[int, dict[str, Any]] | None = None,
) -> None:
    """
    Re-run can_form_edge on persisted proposal edges against current listings.
    Detects stale WANT/HAVE edits that leave inventory still AVAILABLE.
    """
    from .. import db

    rows = listing_rows or {}
    needed: set[int] = set()
    for e in edges_payload:
        needed.add(int(e["source_listing_id"]))
        needed.add(int(e["target_listing_id"]))
    for lid in needed:
        if lid in rows:
            continue
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
        if not row:
            raise GraphIntegrityError("STALE_EDGE", f"Listing {lid} missing for edge revalidation")
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
        rows[lid] = d

    for e in edges_payload:
        src = rows[int(e["source_listing_id"])]
        tgt = rows[int(e["target_listing_id"])]
        ok, reasons = can_form_edge(src, tgt)
        if not ok:
            raise GraphIntegrityError(
                "STALE_EDGE",
                f"Edge {e['source_listing_id']}→{e['target_listing_id']} no longer valid",
                details={"reasons": reasons},
            )
