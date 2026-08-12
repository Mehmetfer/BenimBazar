"""Central kill switch — NO NEW ORDERS when active."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class KillSwitch:
    active: bool = False
    reason: str = ""
    source: str = ""  # runtime | configuration | emergency | risk-triggered
    activated_at: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def activate(self, reason: str, *, source: str = "runtime") -> None:
        self.active = True
        self.reason = reason
        self.source = source
        self.activated_at = datetime.now(timezone.utc).isoformat()
        self.events.append(
            {"ts": self.activated_at, "action": "ACTIVATE", "reason": reason, "source": source}
        )

    def clear(self, *, human_ack: bool = False) -> bool:
        """Clear only with explicit human acknowledgement (fail-closed)."""
        if not human_ack:
            return False
        self.active = False
        self.reason = ""
        self.source = ""
        self.events.append(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": "CLEAR", "human_ack": True}
        )
        return True

    def blocks_new_orders(self) -> tuple[bool, str]:
        if self.active:
            return True, f"KILL_SWITCH:{self.source}:{self.reason}"
        return False, ""
