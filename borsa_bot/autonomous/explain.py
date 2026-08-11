"""Explainable signal cards — features from computed decisions only (no LLM fiction)."""

from __future__ import annotations

from typing import Any


def explain_decision(item: dict[str, Any]) -> dict[str, Any]:
    """Build an explainable payload from serialized SymbolDecision / card fields."""
    decision = item.get("final_decision") or item.get("decision") or item.get("signal") or "NO_TRADE"
    mtf = item.get("mtf") if isinstance(item.get("mtf"), dict) else {}
    confirmed = 0
    for v in mtf.values():
        if str(v).upper() in {"BULL", "BULLISH", "UP", "LONG", "ALIGNED", "BUY"}:
            confirmed += 1
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    opp = item.get("opportunity") if isinstance(item.get("opportunity"), dict) else {}
    plan = item.get("ai_trade_plan") or item.get("trade_plan") or {}
    if not isinstance(plan, dict):
        plan = {}
    entry = item.get("entry")
    if entry is None:
        entry = plan.get("entry") or plan.get("entry_zone")
    stop = item.get("stop") if item.get("stop") is not None else plan.get("stop_loss") or plan.get("stop")
    target = None
    if item.get("targets"):
        target = item["targets"][0]
    if target is None:
        t1 = plan.get("target1")
        if isinstance(t1, dict):
            target = t1.get("price")
        else:
            target = t1 or plan.get("target_1")
    rr = item.get("risk_reward") or opp.get("risk_reward") or plan.get("risk_reward")
    data_kind = item.get("data_source_kind") or item.get("data_status") or "UNKNOWN"
    return {
        "symbol": item.get("symbol"),
        "signal": decision,
        "score": item.get("opportunity_score") or scores.get("final") or item.get("ai_confidence"),
        "confidence": item.get("ai_confidence") or scores.get("ai_confidence"),
        "confidence_label": item.get("confidence_label")
        or "Heuristic / model score — NOT calibrated probability",
        "calibrated_probability": None,
        "probability_note": "confidence ≠ calibrated probability unless sample-validated",
        "trend": item.get("regime") or mtf.get("1h") or mtf.get("4h") or "—",
        "momentum": scores.get("technical") or scores.get("momentum"),
        "volume": scores.get("volume"),
        "mtf": {"confirmed": confirmed, "total": len(mtf), "detail": mtf},
        "market_regime": item.get("regime"),
        "risk": item.get("risk_label") or item.get("risk_verdict") or scores.get("risk"),
        "data": data_kind,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_reward": rr,
        "heuristic": True,
        "ml_model": False,
        "explanation_source": "computed_features",
    }
