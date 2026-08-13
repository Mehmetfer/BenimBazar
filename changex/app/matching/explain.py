"""Human-readable explainability for chain edges."""

from __future__ import annotations

from typing import Any

from .edges import GraphEdge


def explain_edge(source: dict[str, Any], target: dict[str, Any], edge: GraphEdge) -> str:
    have_title = str(target.get("title") or target.get("brand") or target.get("category") or "ürün")
    want_cats = source.get("wanted_categories") or []
    if not isinstance(want_cats, list):
        want_cats = []
    want_label = want_cats[0] if want_cats else str(target.get("category") or "kriter")
    brands = source.get("wanted_brands") or []
    if isinstance(brands, list) and brands:
        return (
            f"{have_title}, {brands[0]} / {want_label} kriterine uyuyor "
            f"(listing #{source.get('id')} → #{target.get('id')})."
        )
    return (
        f"{have_title}, listing #{source.get('id')} kullanıcısının istediği "
        f"{want_label} kriterine uyuyor."
    )


def explain_cycle(
    cycle_edges: list[GraphEdge],
    nodes_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    for edge in cycle_edges:
        src = nodes_by_id.get(edge.source_listing_id, {})
        tgt = nodes_by_id.get(edge.target_listing_id, {})
        out.append(explain_edge(src, tgt, edge))
    return out
