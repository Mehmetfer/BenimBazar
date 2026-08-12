"""Adaptive learning bounded to performance optimization — never safety bypass."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from decision.ade.limits import (
    ADAPTIVE_ALLOWED_FIELDS,
    FROZEN_SAFETY_FIELDS,
    AdaptiveState,
    ImmutableSafetyLimits,
    SafetyBypassError,
)


@dataclass
class LearningOutcome:
    applied: dict[str, Any] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)
    safety_intact: bool = True
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveLearner:
    """Updates soft strategy/signal weights only."""

    def __init__(self, state: AdaptiveState | None = None, limits: ImmutableSafetyLimits | None = None) -> None:
        self.state = state or AdaptiveState()
        self.limits = limits or ImmutableSafetyLimits()
        self._baseline_limits = self.limits

    def learn_from_outcome(
        self,
        *,
        signal_quality: dict[str, float] | None = None,
        strategy_performance: dict[str, float] | None = None,
        false_positive_rate: dict[str, float] | None = None,
        execution_quality: float | None = None,
        slippage_bps: float | None = None,
        provider_reliability: dict[str, float] | None = None,
        attempted_safety_updates: dict[str, Any] | None = None,
    ) -> LearningOutcome:
        updates: dict[str, Any] = {}
        if signal_quality is not None:
            merged = dict(self.state.signal_weights)
            merged.update(signal_quality)
            updates["signal_weights"] = merged
        if strategy_performance is not None:
            merged = dict(self.state.strategy_parameters)
            merged.update(strategy_performance)
            updates["strategy_parameters"] = merged
        if false_positive_rate is not None:
            updates["false_positive_estimates"] = false_positive_rate
        if provider_reliability is not None:
            updates["provider_reliability_scores"] = provider_reliability
        if execution_quality is not None:
            updates["execution_timing_bias"] = float(execution_quality)

        # Explicit attack / misuse path: reject safety mutations
        rejected: list[str] = []
        if attempted_safety_updates:
            for k in attempted_safety_updates:
                if k in FROZEN_SAFETY_FIELDS or k not in ADAPTIVE_ALLOWED_FIELDS:
                    rejected.append(k)

        rejected.extend(self.state.apply_update(updates))
        # de-dupe
        rejected = sorted(set(rejected))

        # Slippage observation never raises max_slippage_bps
        if slippage_bps is not None and slippage_bps > self.limits.max_slippage_bps:
            # record only — do not loosen limit
            pass

        # Prove current limits never loosen past baseline (deployment-controlled only)
        try:
            self._baseline_limits.assert_not_loosened(self.limits)
        except SafetyBypassError:
            return LearningOutcome(
                applied={},
                rejected=rejected + ["limits"],
                safety_intact=False,
                message="limits mutated",
            )

        applied = {k: v for k, v in updates.items() if k not in rejected}
        return LearningOutcome(
            applied=applied,
            rejected=rejected,
            safety_intact=True,
            message="performance optimization only; safety limits unchanged",
        )
