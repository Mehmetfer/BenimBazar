"""Directed cycle detection with max-length bound and owner uniqueness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import CHANGE_CHAIN_MIN_LENGTH, chain_max_length
from .edges import GraphEdge
from .scoring import ScoreBreakdown


@dataclass
class ChainCycle:
    listing_ids: list[int]  # closed: first == implied return via last→first edge
    owner_ids: list[int]
    edges: list[GraphEdge]
    length: int
    overall_score: float
    score_breakdowns: list[dict[str, float]] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)

    def canonical_key(self) -> tuple[int, ...]:
        """Rotate so smallest listing id is first — dedupe equivalent cycles."""
        ids = self.listing_ids
        if not ids:
            return tuple()
        min_i = min(range(len(ids)), key=lambda i: ids[i])
        rotated = ids[min_i:] + ids[:min_i]
        return tuple(rotated)


def _owners_unique(owner_ids: list[int]) -> bool:
    return len(owner_ids) == len(set(owner_ids))


def find_cycles(
    adj: dict[int, list[GraphEdge]],
    nodes_by_id: dict[int, dict[str, Any]],
    *,
    seed_id: int | None = None,
    min_length: int = CHANGE_CHAIN_MIN_LENGTH,
    max_length: int | None = None,
    max_cycles: int = 50,
) -> list[ChainCycle]:
    """
    Bounded DFS cycle search.

    - Rejects self-loops
    - Rejects length < min_length (2-node A→B→A invalid for Chain V1)
    - Enforces max_length
    - Same owner at most once per cycle
    """
    max_len = max_length if max_length is not None else chain_max_length()
    max_len = max(min_length, int(max_len))
    found: dict[tuple[int, ...], ChainCycle] = {}

    starts = [seed_id] if seed_id is not None else list(adj.keys())
    for start in starts:
        if start not in adj:
            continue
        _dfs(
            start=start,
            current=start,
            path_nodes=[start],
            path_owners=[int(nodes_by_id[start]["owner_id"])],
            path_edges=[],
            adj=adj,
            nodes_by_id=nodes_by_id,
            min_length=min_length,
            max_length=max_len,
            found=found,
            max_cycles=max_cycles,
        )
        if len(found) >= max_cycles:
            break

    cycles = list(found.values())
    cycles.sort(key=lambda c: (-c.overall_score, c.length, c.canonical_key()))
    return cycles[:max_cycles]


def _dfs(
    *,
    start: int,
    current: int,
    path_nodes: list[int],
    path_owners: list[int],
    path_edges: list[GraphEdge],
    adj: dict[int, list[GraphEdge]],
    nodes_by_id: dict[int, dict[str, Any]],
    min_length: int,
    max_length: int,
    found: dict[tuple[int, ...], ChainCycle],
    max_cycles: int,
) -> None:
    if len(found) >= max_cycles:
        return
    for edge in adj.get(current, []):
        nxt = edge.target_listing_id
        if nxt == current:
            continue  # self-loop
        if nxt == start:
            length = len(path_nodes)
            if length < min_length or length > max_length:
                continue
            # Closing edge owners already in path_owners; closing doesn't add owner
            if not _owners_unique(path_owners):
                continue
            cycle_edges = path_edges + [edge]
            cycle = _build_cycle(path_nodes, path_owners, cycle_edges)
            key = cycle.canonical_key()
            if key not in found or cycle.overall_score > found[key].overall_score:
                found[key] = cycle
            continue
        if nxt in path_nodes:
            continue
        owner = int(nodes_by_id[nxt]["owner_id"])
        if owner in path_owners:
            continue  # same owner duplication
        if len(path_nodes) + 1 > max_length:
            continue
        path_nodes.append(nxt)
        path_owners.append(owner)
        path_edges.append(edge)
        _dfs(
            start=start,
            current=nxt,
            path_nodes=path_nodes,
            path_owners=path_owners,
            path_edges=path_edges,
            adj=adj,
            nodes_by_id=nodes_by_id,
            min_length=min_length,
            max_length=max_length,
            found=found,
            max_cycles=max_cycles,
        )
        path_nodes.pop()
        path_owners.pop()
        path_edges.pop()


def _build_cycle(
    listing_ids: list[int],
    owner_ids: list[int],
    edges: list[GraphEdge],
) -> ChainCycle:
    breakdowns = [e.score_breakdown.to_dict() for e in edges]
    scores = [e.score for e in edges]
    overall = sum(scores) / len(scores) if scores else 0.0
    # Aggregate component averages for explainability
    agg = ScoreBreakdown()
    if breakdowns:
        n = len(breakdowns)
        agg = ScoreBreakdown(
            category_score=sum(b["category_score"] for b in breakdowns) / n,
            want_score=sum(b["want_score"] for b in breakdowns) / n,
            value_score=sum(b["value_score"] for b in breakdowns) / n,
            location_score=sum(b["location_score"] for b in breakdowns) / n,
            condition_score=sum(b["condition_score"] for b in breakdowns) / n,
            preference_score=sum(b["preference_score"] for b in breakdowns) / n,
        )
    risk: list[str] = []
    if overall < 0.4:
        risk.append("LOW_SCORE")
    if len(listing_ids) >= 4:
        risk.append("LONG_CHAIN")
    return ChainCycle(
        listing_ids=list(listing_ids),
        owner_ids=list(owner_ids),
        edges=list(edges),
        length=len(listing_ids),
        overall_score=overall,
        score_breakdowns=breakdowns,
        risk_flags=risk,
        explanations=[e.reason for e in edges],
    )


def aggregate_chain_score(cycle: ChainCycle) -> dict[str, Any]:
    return {
        "overall_score": cycle.overall_score,
        "edge_scores": [e.score for e in cycle.edges],
        "score_breakdowns": cycle.score_breakdowns,
        "risk_flags": cycle.risk_flags,
        "length": cycle.length,
    }
