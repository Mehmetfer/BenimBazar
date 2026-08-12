"""Circuit breaker — trips on repeated failures; does not auto-resume unboundedly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CircuitBreaker:
    trip_threshold: int = 3
    tripped: bool = False
    reason: str = ""
    failure_counts: dict[str, int] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    recovery_human_ack_required: bool = True

    def record_failure(self, kind: str) -> bool:
        """Record failure; return True if breaker trips."""
        k = (kind or "UNKNOWN").upper()
        self.failure_counts[k] = self.failure_counts.get(k, 0) + 1
        if self.failure_counts[k] >= self.trip_threshold:
            self.trip(f"REPEATED_{k}")
            return True
        return self.tripped

    def trip(self, reason: str) -> None:
        self.tripped = True
        self.reason = reason
        self.events.append(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": "TRIP", "reason": reason}
        )

    def reset(self, *, human_ack: bool = False) -> bool:
        if self.recovery_human_ack_required and not human_ack:
            return False
        self.tripped = False
        self.reason = ""
        self.failure_counts.clear()
        self.events.append(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": "RESET", "human_ack": human_ack}
        )
        return True

    def blocks_new_orders(self) -> tuple[bool, str]:
        if self.tripped:
            return True, f"CIRCUIT_BREAKER:{self.reason}"
        return False, ""
