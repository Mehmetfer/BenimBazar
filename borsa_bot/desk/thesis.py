"""Trade thesis builder — required context before opening a position."""

from __future__ import annotations

from typing import Any

from desk.models import AnalystVote, TradeThesis


def build_thesis(
    row: dict[str, Any],
    votes: list[AnalystVote],
    *,
    consensus_decision: str,
    confidence: float,
) -> TradeThesis:
    sym = str(row.get("symbol") or "")
    opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
    plan = row.get("trade_plan") if isinstance(row.get("trade_plan"), dict) else {}
    if not plan and isinstance(row.get("ai_trade_plan"), dict):
        plan = row["ai_trade_plan"]

    stop = row.get("stop_price") or plan.get("stop")
    target = row.get("target_price") or plan.get("target_1") or plan.get("target")

    bull_votes = [v for v in votes if v.decision in {"BUY", "APPROVE", "GO"}]
    why_parts = [v.reason for v in bull_votes[:3] if v.reason]
    why = "; ".join(why_parts) if why_parts else str(row.get("explanation") or "structured_edge")

    inv_parts = [v.risk for v in votes if v.risk]
    invalidation = "; ".join(inv_parts[:4]) if inv_parts else "stop_or_thesis_break"

    return TradeThesis(
        symbol=sym,
        why=why[:500],
        catalyst=str(row.get("regime") or plan.get("catalyst") or "technical_setup"),
        horizon=str(plan.get("horizon") or "SWING"),
        invalidation=invalidation[:300],
        target=float(target) if target else None,
        stop=float(stop) if stop else None,
        expected_edge=float(opp.get("expected_value")) if opp.get("expected_value") is not None else None,
        risk="; ".join(row.get("risks") or [])[:200] if isinstance(row.get("risks"), list) else str(row.get("risk") or ""),
        confidence=confidence,
        analyst_votes=[v.to_dict() for v in votes],
    )
