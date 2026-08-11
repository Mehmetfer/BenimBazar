"""Phase 1 — AutonomyGovernor: dynamic autonomy ceiling (never raises risk limits)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from config.settings import settings


class AutonomyState(str, Enum):
    OFFLINE = "OFFLINE"
    OBSERVE = "OBSERVE"
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    CONTROLLED_LIVE = "CONTROLLED_LIVE"
    LIVE = "LIVE"
    RESTRICTED = "RESTRICTED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


_DEGRADE = {
    "NORMAL": AutonomyState.PAPER,
    "CAUTION": AutonomyState.RESTRICTED,
    "RESTRICTED": AutonomyState.OBSERVE,
    "PAPER_ONLY": AutonomyState.PAPER,
    "EMERGENCY_STOP": AutonomyState.EMERGENCY_STOP,
}


@dataclass
class AutonomyGovernorVerdict:
    state: str
    tier: str  # NORMAL | CAUTION | RESTRICTED | PAPER_ONLY | EMERGENCY_STOP
    allow_research: bool
    allow_paper: bool
    allow_shadow: bool
    allow_live: bool
    size_mult_cap: float
    reasons: list[str] = field(default_factory=list)
    note: str = "AutonomyGovernor never unlocks LIVE broker or raises risk limits"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomyGovernor:
    """Central autonomy ceiling. AI cannot disable kill switch or force LIVE."""

    def evaluate(
        self,
        *,
        context: dict[str, Any] | None = None,
        system_health: dict[str, Any] | None = None,
        prediction_tier: str | None = None,
        model_disagreement: bool = False,
        loss_governor_state: str | None = None,
        data_quality: float | None = None,
    ) -> AutonomyGovernorVerdict:
        ctx = context or {}
        health = system_health or {}
        reasons: list[str] = []
        size_cap = 1.0
        tier = "NORMAL"
        state = AutonomyState.PAPER  # default safe autonomous stage

        if settings.kill_switch or ctx.get("kill_switch"):
            return AutonomyGovernorVerdict(
                AutonomyState.EMERGENCY_STOP.value,
                "EMERGENCY_STOP",
                False,
                False,
                False,
                False,
                0.0,
                ["KILL_SWITCH"],
            )

        if loss_governor_state in {"TRADING_HALT"}:
            return AutonomyGovernorVerdict(
                AutonomyState.EMERGENCY_STOP.value,
                "EMERGENCY_STOP",
                True,
                False,
                False,
                False,
                0.0,
                ["LOSS_GOVERNOR_HALT"],
            )

        hscore = health.get("health_score")
        if hscore is not None and float(hscore) < 40:
            return AutonomyGovernorVerdict(
                AutonomyState.EMERGENCY_STOP.value,
                "EMERGENCY_STOP",
                False,
                False,
                False,
                False,
                0.0,
                ["SYSTEM_HEALTH_CRITICAL"],
            )

        kind = str(ctx.get("data_kind") or "").upper()
        if not ctx.get("data_valid", True) or kind in {"UNKNOWN", "INVALID", "MOCK"}:
            reasons.append("DATA_INVALID")
            tier = "RESTRICTED"
            state = AutonomyState.OBSERVE
            size_cap = 0.0
        elif not ctx.get("data_fresh", True) and kind not in {"SIMULATED"}:
            reasons.append("DATA_STALE")
            tier = "RESTRICTED"
            state = AutonomyState.OBSERVE
            size_cap = 0.0

        if data_quality is not None and data_quality < 50:
            reasons.append("LOW_DATA_QUALITY")
            tier = "CAUTION" if tier == "NORMAL" else tier
            size_cap = min(size_cap, 0.5)

        pred = str(prediction_tier or ctx.get("prediction_tier") or "").upper()
        if pred in {"INSUFFICIENT", "POOR", "INSUFFICIENT_DATA"}:
            reasons.append("PREDICTION_QUALITY_LOW")
            tier = "CAUTION" if tier == "NORMAL" else tier
            size_cap = min(size_cap, 0.75)

        if model_disagreement:
            reasons.append("MODEL_DISAGREEMENT")
            tier = "CAUTION" if tier == "NORMAL" else tier
            size_cap = min(size_cap, 0.65)

        labels = {str(x).upper() for x in (ctx.get("regime_labels") or [])}
        if "HIGH_VOLATILITY" in labels:
            reasons.append("HIGH_VOLATILITY")
            tier = "CAUTION" if tier == "NORMAL" else tier
            size_cap = min(size_cap, 0.6)

        if loss_governor_state in {"CAUTION", "REDUCED_RISK"}:
            reasons.append(f"LOSS_GOVERNOR_{loss_governor_state}")
            if loss_governor_state == "REDUCED_RISK":
                tier = "RESTRICTED"
                state = AutonomyState.RESTRICTED
                size_cap = min(size_cap, 0.35)
            else:
                tier = "CAUTION" if tier == "NORMAL" else tier
                size_cap = min(size_cap, 0.55)

        if hscore is not None and float(hscore) < 70:
            reasons.append("SYSTEM_HEALTH_CAUTION")
            tier = "CAUTION" if tier == "NORMAL" else tier
            size_cap = min(size_cap, 0.5)

        # LIVE never allowed by this governor
        allow_live = False
        reasons.append("LIVE_BROKER_LOCKED")

        if tier == "NORMAL":
            state = AutonomyState.PAPER
        elif tier == "CAUTION":
            state = AutonomyState.RESTRICTED if state != AutonomyState.OBSERVE else state
        elif tier == "RESTRICTED" and state not in {AutonomyState.OBSERVE, AutonomyState.EMERGENCY_STOP}:
            state = AutonomyState.RESTRICTED

        allow_research = state not in {AutonomyState.OFFLINE, AutonomyState.EMERGENCY_STOP}
        allow_paper = state in {
            AutonomyState.PAPER,
            AutonomyState.SHADOW,
            AutonomyState.RESTRICTED,
            AutonomyState.CONTROLLED_LIVE,
        } and size_cap > 0
        # RESTRICTED may still research; paper only if size_cap > 0 and not OBSERVE
        if state in {AutonomyState.OBSERVE, AutonomyState.EMERGENCY_STOP, AutonomyState.OFFLINE}:
            allow_paper = False
        allow_shadow = state in {AutonomyState.SHADOW, AutonomyState.CONTROLLED_LIVE} and allow_paper

        if not reasons:
            reasons = ["ok"]

        return AutonomyGovernorVerdict(
            state=state.value,
            tier=tier,
            allow_research=allow_research,
            allow_paper=allow_paper,
            allow_shadow=allow_shadow,
            allow_live=allow_live,
            size_mult_cap=round(size_cap, 3),
            reasons=reasons,
        )


autonomy_governor = AutonomyGovernor()
