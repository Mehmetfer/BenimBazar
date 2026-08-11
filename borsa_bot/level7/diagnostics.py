"""Phase 10 — Self-diagnostics + Level 7 scorecard."""

from __future__ import annotations

from typing import Any

from level7.autonomy_governor import AutonomyGovernorVerdict
from level7.store import Level7Store


class SelfDiagnostics:
    agent_id = "SelfDiagnostics"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()

    def diagnose(
        self,
        *,
        autonomy: AutonomyGovernorVerdict | dict[str, Any] | None = None,
        learning: dict[str, Any] | None = None,
        health: dict[str, Any] | None = None,
        experiments: list[dict] | None = None,
        strategies: list[dict] | None = None,
        recent_eval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        autonomy = autonomy.to_dict() if hasattr(autonomy, "to_dict") else (autonomy or {})
        learning = learning or {}
        health = health or {}
        experiments = experiments or []
        strategies = strategies or []
        recent_eval = recent_eval or {}

        bad: list[str] = []
        good: list[str] = []

        tier = str(learning.get("sample_tier") or learning.get("grade") or "INSUFFICIENT").upper()
        if tier in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
            bad.append("Prediction sample insufficient — cannot claim calibrated probabilities")
        else:
            good.append(f"Prediction tier {tier}")

        if autonomy.get("tier") in {"CAUTION", "RESTRICTED", "EMERGENCY_STOP"}:
            bad.append(f"Autonomy degraded: {autonomy.get('tier')} ({', '.join(autonomy.get('reasons') or [])})")
        else:
            good.append("Autonomy tier NORMAL/PAPER-capable")

        h = health.get("health_score")
        if h is not None and float(h) < 70:
            bad.append(f"System health {h} — caution")
        elif h is not None:
            good.append(f"System health {h}")

        failed_ex = [e for e in experiments if e.get("status") == "FAILED"]
        if failed_ex:
            bad.append(f"{len(failed_ex)} failed experiments — review hypotheses")
        blocked = [e for e in experiments if e.get("status") == "BLOCKED"]
        if blocked:
            bad.append(f"{len(blocked)} experiments blocked (sample/significance)")

        drift = [s for s in strategies if "STRATEGY_DRIFT" in str(s.get("performance_json") or "")]
        if drift:
            bad.append("Strategy drift detected on one or more strategies")

        if recent_eval.get("sample_sufficient") is False:
            bad.append("Self-eval window too small for strong claims")

        if not bad:
            bad.append("No acute failures — still avoid guarantee language")

        return {
            "what_am_i_doing_badly": bad,
            "what_is_working": good,
            "recommendations": [
                "Keep fail-closed on stale/invalid data",
                "Advance challengers only via paper→shadow→human approval",
                "Prefer NO_TRADE under model conflict",
                "Do not raise risk limits when losing",
            ],
            "can_modify_production_code": False,
            "can_disable_kill_switch": False,
            "can_raise_risk_limits": False,
            "can_auto_promote_models": False,
        }


def level7_scorecard(
    *,
    data_integrity: float,
    research_n: int,
    hypothesis_n: int,
    experiment_n: int,
    decision_quality_avg: float,
    risk_awareness: float,
    learning_tier: str,
    diagnostics_ok: bool,
    execution_safety: float = 95.0,
    autonomy_tier: str = "NORMAL",
) -> dict[str, Any]:
    research = min(95.0, 40 + research_n * 5 + hypothesis_n * 3 + experiment_n * 4)
    decision = float(decision_quality_avg or 55)
    risk = float(risk_awareness or 90)
    learn = {
        "EXCELLENT": 85,
        "GOOD": 75,
        "FAIR": 60,
        "POOR": 40,
        "INSUFFICIENT": 35,
        "INSUFFICIENT_DATA": 35,
    }.get(str(learning_tier).upper(), 45)
    self_diag = 80.0 if diagnostics_ok else 50.0
    data = float(data_integrity or 50)
    exec_s = float(execution_safety)

    # Cap overall: cannot claim Level 7 maturity without live gates + calibrated learning
    total = round((data + research + decision + risk + learn + self_diag + exec_s) / 7, 1)
    if str(learning_tier).upper() in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
        total = min(total, 72.0)
    if autonomy_tier in {"EMERGENCY_STOP", "RESTRICTED"}:
        total = min(total, 65.0)
    # Honest: architecture Level 7 features present, operational maturity lower
    claimed_level = 4  # research/self-eval layer
    if total >= 80 and str(learning_tier).upper() in {"GOOD", "EXCELLENT", "FAIR"}:
        claimed_level = 5
    # Never claim full Level 7 / autonomous live
    maturity_label = {
        4: "SELF_EVAL_RESEARCH_LAYER",
        5: "SHADOW_READY_CANDIDATE",
        6: "CONTROLLED_LIVE_CANDIDATE",
        7: "SELF_EVOLVING_LIVE",  # never assigned here
    }.get(claimed_level, "SELF_EVAL_RESEARCH_LAYER")

    return {
        "level7_autonomy_score": total,
        "research_intelligence": round(research, 1),
        "decision_intelligence": round(decision, 1),
        "risk_intelligence": round(risk, 1),
        "learning_intelligence": round(float(learn), 1),
        "self_diagnostic_score": round(self_diag, 1),
        "data_integrity": round(data, 1),
        "execution_safety": round(exec_s, 1),
        "operational_maturity_level": claimed_level,
        "maturity_label": maturity_label,
        "full_level7_claimed": False,
        "note": (
            "Level 7 architecture modules present (research→hypothesis→experiment→propose). "
            "Full Level 7 LIVE self-evolution is NOT claimed — human approval + calibrated history required."
        ),
    }
