"""AI activity timeline — human-readable audit steps (no fake market events)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config.models import utc_now


@dataclass
class ActivityEvent:
    ts: str
    message: str
    symbol: str | None = None
    level: str = "INFO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActivityLog:
    events: list[ActivityEvent] = field(default_factory=list)

    def add(self, message: str, *, symbol: str | None = None, level: str = "INFO") -> None:
        self.events.append(ActivityEvent(ts=utc_now().isoformat(), message=message, symbol=symbol, level=level))

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events[-80:]]
