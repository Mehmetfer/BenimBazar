"""Observability counters — do not replace trading decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TradingMetrics:
    decision_latency_ms: list[float] = field(default_factory=list)
    execution_latency_ms: list[float] = field(default_factory=list)
    provider_latency_ms: list[float] = field(default_factory=list)
    stale_data_events: int = 0
    rejections: int = 0
    recovery_count: int = 0
    reconciliation_mismatches: int = 0
    duplicate_prevented: int = 0
    circuit_breaker_events: int = 0
    kill_switch_events: int = 0
    order_success: int = 0
    order_failure: int = 0
    unknown_order_events: int = 0

    def record_reject(self) -> None:
        self.rejections += 1

    def record_duplicate(self) -> None:
        self.duplicate_prevented += 1

    def snapshot(self) -> dict[str, Any]:
        def avg(xs: list[float]) -> float | None:
            return (sum(xs) / len(xs)) if xs else None

        return {
            "decision_latency_ms_avg": avg(self.decision_latency_ms),
            "execution_latency_ms_avg": avg(self.execution_latency_ms),
            "provider_latency_ms_avg": avg(self.provider_latency_ms),
            "stale_data_events": self.stale_data_events,
            "rejections": self.rejections,
            "recovery_count": self.recovery_count,
            "reconciliation_mismatches": self.reconciliation_mismatches,
            "duplicate_prevented": self.duplicate_prevented,
            "circuit_breaker_events": self.circuit_breaker_events,
            "kill_switch_events": self.kill_switch_events,
            "order_success": self.order_success,
            "order_failure": self.order_failure,
            "unknown_order_events": self.unknown_order_events,
        }
