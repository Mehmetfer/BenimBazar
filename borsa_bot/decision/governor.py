"""AIGovernor — ALLOW / LIMIT / BLOCK between AI proposals and risk/execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config.settings import settings


@dataclass
class GovernorDecision:
    verdict: str  # ALLOW | LIMIT | BLOCK
    reasons: list[str]
    size_mult_cap: float
    allow_strong_buy: bool
    note: str = "Governor cannot grant risk bypass"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIGovernor:
    """Controls AI autonomy vs data/health/model quality. Never unlocks LIVE broker."""

    def evaluate(
        self,
        *,
        context: dict[str, Any],
        regime: dict[str, Any] | None = None,
        debate: dict[str, Any] | None = None,
        system_health: dict[str, Any] | None = None,
        model_tier: str | None = None,
    ) -> GovernorDecision:
        reasons: list[str] = []
        size_cap = 1.0
        allow_strong = True

        if settings.kill_switch:
            return GovernorDecision("BLOCK", ["KILL_SWITCH"], 0.0, False)

        if not context.get("data_valid", False):
            return GovernorDecision("BLOCK", ["DATA_INVALID"], 0.0, False)

        if context.get("kill_switch"):
            return GovernorDecision("BLOCK", ["KILL_SWITCH"], 0.0, False)

        if context.get("risk_paused"):
            return GovernorDecision("BLOCK", ["RISK_PAUSED"], 0.0, False)

        kind = str(context.get("data_kind") or "").upper()
        if settings.is_production and kind in {"SIMULATED", "TEST", "MOCK", "UNKNOWN"}:
            return GovernorDecision("BLOCK", [f"PRODUCTION_DATA_{kind}"], 0.0, False)

        if not context.get("data_fresh", True) and kind not in {"SIMULATED"}:
            return GovernorDecision("BLOCK", ["DATA_STALE"], 0.0, False)

        health = system_health or {}
        hscore = health.get("health_score")
        if hscore is not None and float(hscore) < 40:
            return GovernorDecision("BLOCK", ["SYSTEM_HEALTH_CRITICAL"], 0.0, False)
        if hscore is not None and float(hscore) < 70:
            reasons.append("SYSTEM_HEALTH_CAUTION")
            size_cap = min(size_cap, 0.5)
            allow_strong = False

        regime = regime or {}
        labels = {str(x).upper() for x in (regime.get("labels") or [])}
        if "HIGH_VOLATILITY" in labels:
            reasons.append("HIGH_VOLATILITY_LIMIT")
            size_cap = min(size_cap, 0.6)
            allow_strong = False
        if float(regime.get("confidence") or 1) < 0.45:
            reasons.append("LOW_REGIME_CONFIDENCE")
            size_cap = min(size_cap, 0.7)
            allow_strong = False

        debate = debate or {}
        if debate.get("data_conflict"):
            reasons.append("DEBATE_MTF_CONFLICT")
            size_cap = min(size_cap, 0.65)
            allow_strong = False
        if debate.get("overconfidence_risk"):
            reasons.append("OVERCONFIDENCE_LIMIT")
            size_cap = min(size_cap, 0.7)
            allow_strong = False
        if not debate.get("bull_beats_bear", True):
            reasons.append("BEAR_CASE_DOMINANT")
            size_cap = min(size_cap, 0.5)
            allow_strong = False

        tier = str(model_tier or context.get("prediction_tier") or "").upper()
        if tier in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
            reasons.append("MODEL_SAMPLE_INSUFFICIENT")
            size_cap = min(size_cap, 0.75)
            allow_strong = False

        # LIVE broker never allowed by governor
        if getattr(settings, "live_broker_enabled", False) is False:
            reasons.append("LIVE_BROKER_LOCKED")

        verdict = "LIMIT" if reasons else "ALLOW"
        if size_cap <= 0:
            verdict = "BLOCK"
        return GovernorDecision(
            verdict=verdict,
            reasons=reasons or ["ok"],
            size_mult_cap=round(size_cap, 3),
            allow_strong_buy=allow_strong,
            note="ALLOW/LIMIT still require RiskEngine + PreTradeGate",
        )


ai_governor = AIGovernor()
