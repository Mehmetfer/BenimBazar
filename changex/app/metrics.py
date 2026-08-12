"""Domain metrics for CHANGE X Core (feeds future Change Score / Chain)."""

from __future__ import annotations

from typing import Any

from .states import TradeState


def compute_trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "offers_total": 0,
            "offer_conversion": 0.0,
            "completion_rate": 0.0,
            "cancellation_rate": 0.0,
            "dispute_rate": 0.0,
            "average_trade_value_mandal": 0.0,
            "average_gap_mandal": 0.0,
            "average_time_to_trade_seconds": None,
        }

    statuses = [str(r.get("status") or r.get("state") or "") for r in rows]
    offered_like = sum(1 for s in statuses if s)
    accepted = sum(
        1
        for s in statuses
        if s
        in {
            TradeState.ACCEPTED.value,
            TradeState.CONFIRMED.value,
            TradeState.IN_TRANSFER.value,
            TradeState.DELIVERED.value,
            TradeState.COMPLETED.value,
        }
    )
    completed = sum(1 for s in statuses if s == TradeState.COMPLETED.value)
    cancelled = sum(1 for s in statuses if s == TradeState.CANCELLED.value)
    disputed = sum(1 for s in statuses if s == TradeState.DISPUTED.value)

    values = [
        int(r.get("calculated_requested_mandal_units") or 0) for r in rows
    ]
    gaps = [abs(int(r.get("value_gap_mandal_units") or 0)) for r in rows]

    ttt: list[float] = []
    for r in rows:
        if r.get("completed_at") and r.get("created_at"):
            ttt.append(float(r["completed_at"]) - float(r["created_at"]))

    return {
        "offers_total": offered_like,
        "offer_conversion": (accepted / offered_like) if offered_like else 0.0,
        "completion_rate": (completed / accepted) if accepted else 0.0,
        "cancellation_rate": (cancelled / offered_like) if offered_like else 0.0,
        "dispute_rate": (disputed / offered_like) if offered_like else 0.0,
        "average_trade_value_mandal": (sum(values) / len(values)) if values else 0.0,
        "average_gap_mandal": (sum(gaps) / len(gaps)) if gaps else 0.0,
        "average_time_to_trade_seconds": (sum(ttt) / len(ttt)) if ttt else None,
    }
