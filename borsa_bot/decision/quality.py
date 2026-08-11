"""Decision quality + autonomy scoring (explainable 0–100 components)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DecisionQuality:
    data_quality: float
    mtf_alignment: float
    regime_alignment: float
    liquidity: float
    risk_reward: float
    model_agreement: float
    counter_risk: float
    debate_edge: float
    total: float
    eligible_strong_buy: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_decision_quality(
    *,
    row: dict[str, Any],
    context: dict[str, Any],
    debate: dict[str, Any] | None = None,
    regime: dict[str, Any] | None = None,
) -> DecisionQuality:
    debate = debate or {}
    regime = regime or {}
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
    notes: list[str] = []

    data_q = 95.0 if context.get("data_valid") and context.get("data_fresh") else (
        70.0 if context.get("data_valid") else 20.0
    )
    if str(context.get("data_kind") or "").upper() == "SIMULATED":
        data_q = min(data_q, 60.0)
        notes.append("SIMULATED_DATA_CAP")

    mtf = row.get("mtf") if isinstance(row.get("mtf"), dict) else {}
    vals = {str(v).upper() for v in mtf.values()}
    buys = any(v in {"BULL", "BULLISH", "BUY", "UP"} for v in vals)
    sells = any(v in {"BEAR", "BEARISH", "SELL", "DOWN"} for v in vals)
    if buys and sells:
        mtf_s = 40.0
        notes.append("MTF_CONFLICT")
    elif buys or sells:
        mtf_s = 91.0
    else:
        mtf_s = 55.0

    primary = str(regime.get("primary") or row.get("regime") or "").upper()
    action = str(row.get("final_decision") or row.get("decision") or "").upper()
    if action in {"BUY", "STRONG_BUY", "AL"} and primary in {"BEAR", "STRONG_BEAR"}:
        regime_s = 45.0
        notes.append("REGIME_MISALIGN")
    elif action in {"BUY", "STRONG_BUY", "AL"} and primary in {"BULL", "STRONG_BULL"}:
        regime_s = 88.0
    else:
        regime_s = 70.0

    liq = float(scores.get("liquidity") or 50)
    rr = float(opp.get("risk_reward") or row.get("risk_reward") or 1.0)
    rr_s = min(100.0, max(20.0, rr * 35))
    model_agree = 81.0 if debate.get("bull_beats_bear") else 55.0
    if debate.get("data_conflict"):
        model_agree = min(model_agree, 50.0)
    counter = 76.0
    if debate.get("overconfidence_risk"):
        counter = 50.0
    if debate.get("confirmation_bias_risk"):
        counter = min(counter, 55.0)
    debate_edge = max(0.0, float(debate.get("bull_score") or 0) - float(debate.get("bear_score") or 0))
    debate_s = min(100.0, 50.0 + debate_edge)

    parts = [data_q, mtf_s, regime_s, liq, rr_s, model_agree, counter, debate_s]
    total = round(sum(parts) / len(parts), 1)

    eligible = (
        data_q >= 85
        and mtf_s >= 85
        and regime_s >= 70
        and liq >= 60
        and rr >= 2.0
        and float(opp.get("expected_value") or 0) > 0
        and bool(debate.get("bull_beats_bear"))
        and not debate.get("data_conflict")
        and not debate.get("overconfidence_risk")
        and total >= 80
    )
    if not eligible:
        notes.append("STRONG_BUY_STANDARD_NOT_MET")

    return DecisionQuality(
        data_quality=round(data_q, 1),
        mtf_alignment=round(mtf_s, 1),
        regime_alignment=round(regime_s, 1),
        liquidity=round(liq, 1),
        risk_reward=round(rr_s, 1),
        model_agreement=round(model_agree, 1),
        counter_risk=round(counter, 1),
        debate_edge=round(debate_s, 1),
        total=total,
        eligible_strong_buy=eligible,
        notes=notes,
    )


def autonomy_dashboard_scores(
    *,
    context_ok: bool,
    discovery_n: int,
    decisions_n: int,
    prediction_tier: str,
    risk_awareness: float = 90.0,
) -> dict[str, Any]:
    market_u = 88 if context_ok else 40
    opp = min(95, 50 + min(40, discovery_n))
    reasoning = 82 if decisions_n else 50
    pred = {
        "EXCELLENT": 88,
        "GOOD": 78,
        "FAIR": 65,
        "POOR": 45,
        "INSUFFICIENT": 40,
        "INSUFFICIENT_DATA": 40,
    }.get(str(prediction_tier).upper(), 55)
    adapt = 70
    self_eval = 75 if pred >= 55 else 50
    total = round((market_u + opp + reasoning + risk_awareness + pred + adapt + self_eval) / 7, 1)
    level = 2
    if total >= 85 and context_ok:
        level = 4
    elif total >= 75:
        level = 3
    elif total >= 55:
        level = 2
    elif total >= 35:
        level = 1
    else:
        level = 0
    return {
        "market_understanding": market_u,
        "opportunity_discovery": opp,
        "reasoning": reasoning,
        "risk_awareness": risk_awareness,
        "prediction_accuracy": pred,
        "adaptability": adapt,
        "self_evaluation": self_eval,
        "total_autonomy": total,
        "autonomy_level": level,
        "autonomy_label": {
            0: "STATIC_RULES",
            1: "AI_ASSISTANT",
            2: "AI_ANALYST",
            3: "AI_DECISION_ENGINE",
            4: "AUTONOMOUS_RESEARCH_AGENT",
            5: "AUTONOMOUS_TRADING_INTELLIGENCE",
            6: "CONTROLLED_AUTONOMOUS_TRADING",
        }.get(level, "AI_ANALYST"),
        "note": "Level 5–6 require shadow/live gates + calibrated models — not claimed here",
    }
