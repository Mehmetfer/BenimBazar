"""Immutable safety limits — bot learning MUST NOT mutate these in production."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, FrozenSet


# Fields learning / adaptive layers are forbidden from changing.
FROZEN_SAFETY_FIELDS: FrozenSet[str] = frozenset(
    {
        "hard_max_position_size",
        "hard_max_position_notional",
        "hard_max_daily_loss_pct",
        "hard_max_exposure_pct",
        "hard_max_trades_per_day",
        "kill_switch_active",
        "fail_closed",
        "confidence_threshold",
        "min_expected_value",
        "max_slippage_bps",
        "live_broker_enabled",
        "authentication_required",
        "authorization_required",
        "audit_required",
    }
)

# Soft parameters adaptive learning MAY tune (performance only).
ADAPTIVE_ALLOWED_FIELDS: FrozenSet[str] = frozenset(
    {
        "signal_weights",
        "strategy_parameters",
        "regime_classification_bias",
        "execution_timing_bias",
        "provider_reliability_scores",
        "false_positive_estimates",
    }
)


@dataclass(frozen=True)
class ImmutableSafetyLimits:
    """Hard safety envelope. Instances are frozen; clone via controlled deployment only."""

    hard_max_position_size: float = 100.0
    hard_max_position_notional: float = 50_000.0
    hard_max_daily_loss_pct: float = 2.0
    hard_max_exposure_pct: float = 25.0
    hard_max_trades_per_day: int = 20
    kill_switch_active: bool = False
    fail_closed: bool = True
    confidence_threshold: float = 0.55
    min_expected_value: float = 0.0
    max_slippage_bps: float = 50.0
    live_broker_enabled: bool = False
    authentication_required: bool = True
    authorization_required: bool = True
    audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def assert_not_loosened(self, other: ImmutableSafetyLimits) -> None:
        """Raise if `other` weakens any hard constraint relative to self."""
        if other.hard_max_position_size > self.hard_max_position_size:
            raise SafetyBypassError("hard_max_position_size cannot be increased by learning")
        if other.hard_max_position_notional > self.hard_max_position_notional:
            raise SafetyBypassError("hard_max_position_notional cannot be increased by learning")
        if other.hard_max_daily_loss_pct > self.hard_max_daily_loss_pct:
            raise SafetyBypassError("hard_max_daily_loss_pct cannot be increased by learning")
        if other.hard_max_exposure_pct > self.hard_max_exposure_pct:
            raise SafetyBypassError("hard_max_exposure_pct cannot be increased by learning")
        if other.hard_max_trades_per_day > self.hard_max_trades_per_day:
            raise SafetyBypassError("hard_max_trades_per_day cannot be increased by learning")
        if self.kill_switch_active and not other.kill_switch_active:
            raise SafetyBypassError("kill_switch cannot be cleared by learning")
        if self.fail_closed and not other.fail_closed:
            raise SafetyBypassError("fail_closed cannot be disabled by learning")
        if other.confidence_threshold < self.confidence_threshold:
            raise SafetyBypassError("confidence_threshold cannot be lowered by learning")
        if other.min_expected_value < self.min_expected_value:
            raise SafetyBypassError("min_expected_value cannot be lowered by learning")
        if other.max_slippage_bps > self.max_slippage_bps:
            raise SafetyBypassError("max_slippage_bps cannot be raised by learning")
        if other.live_broker_enabled and not self.live_broker_enabled:
            raise SafetyBypassError("live_broker_enabled cannot be enabled by learning")


class SafetyBypassError(RuntimeError):
    """Raised when adaptive code attempts to mutate immutable safety controls."""


@dataclass
class AdaptiveState:
    """Mutable performance-optimization state (never safety limits)."""

    signal_weights: dict[str, float] = field(default_factory=lambda: {"trend": 1.0, "mean_rev": 1.0})
    strategy_parameters: dict[str, float] = field(default_factory=dict)
    regime_classification_bias: dict[str, float] = field(default_factory=dict)
    execution_timing_bias: float = 0.0
    provider_reliability_scores: dict[str, float] = field(default_factory=dict)
    false_positive_estimates: dict[str, float] = field(default_factory=dict)

    def apply_update(self, updates: dict[str, Any]) -> list[str]:
        """Apply only allowed adaptive fields. Returns rejected keys."""
        rejected: list[str] = []
        for key, value in updates.items():
            if key in FROZEN_SAFETY_FIELDS:
                rejected.append(key)
                continue
            if key not in ADAPTIVE_ALLOWED_FIELDS:
                rejected.append(key)
                continue
            setattr(self, key, value)
        return rejected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
