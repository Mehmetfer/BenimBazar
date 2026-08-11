"""Level 8 scorecard — honest continuous-learning maturity (not LIVE Level 8 claim)."""

from __future__ import annotations

from typing import Any


def level8_scorecard(
    *,
    data_integrity: float,
    research_score: float,
    self_diagnostic: float,
    model_adaptation: float,
    strategy_adaptation: float,
    risk_safety: float,
    learning_loop_ok: bool,
    prediction_tier: str = "INSUFFICIENT",
    experiments: int = 0,
    validated_hypotheses: int = 0,
    rejected_hypotheses: int = 0,
    active_challengers: int = 0,
    promotion_candidates: int = 0,
    drifts: int = 0,
    patterns: int = 0,
    root_causes: int = 0,
) -> dict[str, Any]:
    learn = (
        40
        + (15 if learning_loop_ok else 0)
        + min(20, experiments * 2)
        + min(15, validated_hypotheses * 5)
        + min(10, patterns)
    )
    # Cap when prediction history insufficient
    if str(prediction_tier).upper() in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
        learn = min(learn, 68)
        model_adaptation = min(model_adaptation, 55)
    total = round(
        (
            float(data_integrity)
            + float(research_score)
            + float(self_diagnostic)
            + float(model_adaptation)
            + float(strategy_adaptation)
            + float(risk_safety)
            + float(learn)
        )
        / 7,
        1,
    )
    # Never claim operational Level 8 LIVE self-adaptation
    maturity = 5 if total >= 75 and learning_loop_ok else 4
    if str(prediction_tier).upper() in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
        maturity = min(maturity, 5)

    return {
        "continuous_learning_score": total,
        "research_score": round(float(research_score), 1),
        "self_diagnostic_score": round(float(self_diagnostic), 1),
        "model_adaptation_score": round(float(model_adaptation), 1),
        "strategy_adaptation_score": round(float(strategy_adaptation), 1),
        "data_integrity": round(float(data_integrity), 1),
        "risk_safety": round(float(risk_safety), 1),
        "learning_intelligence": round(float(learn), 1),
        "operational_maturity_level": maturity,
        "maturity_label": {
            4: "CONTINUOUS_RESEARCH_LAYER",
            5: "PAPER_SHADOW_LEARNING",
            6: "CONTROLLED_LIVE_LEARNING",
            8: "FULL_CONTINUOUS_LIVE",  # never assigned
        }.get(maturity, "CONTINUOUS_RESEARCH_LAYER"),
        "full_level8_claimed": False,
        "stats": {
            "total_experiments": experiments,
            "validated_hypotheses": validated_hypotheses,
            "rejected_hypotheses": rejected_hypotheses,
            "active_challengers": active_challengers,
            "promotion_candidates": promotion_candidates,
            "retired_models": 0,
            "detected_drifts": drifts,
            "learned_patterns": patterns,
            "root_causes": root_causes,
        },
        "governance": {
            "learning_authority": "HIGH",
            "production_mutate": "RESTRICTED",
            "risk_limits": "DENIED",
            "kill_switch": "DENIED",
            "broker_permissions": "DENIED",
            "auto_promotion": False,
        },
        "note": (
            "Level 8 continuous learning modules present. "
            "Full LIVE continuous self-adaptation is NOT claimed — human approval required."
        ),
    }
