from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CooldownGate:
    """Prevents spam for the same symbol+event under identical conditions."""

    default_seconds: int = 300
    _last: dict[str, float] = field(default_factory=dict)

    def allow(self, key: str, seconds: int | None = None) -> bool:
        window = self.default_seconds if seconds is None else seconds
        now = time.time()
        last = self._last.get(key)
        if last is not None and (now - last) < window:
            return False
        self._last[key] = now
        return True

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._last.clear()
        else:
            self._last.pop(key, None)


@dataclass
class Deduper:
    """One logical event → one event_id across PUSH/SMS/SOUND deliveries."""

    ttl_seconds: float = 60.0
    _seen: dict[str, float] = field(default_factory=dict)

    def seen_or_mark(self, event_id: str) -> bool:
        """Return True if already processed (duplicate)."""
        now = time.time()
        self._seen = {k: t for k, t in self._seen.items() if now - t < self.ttl_seconds}
        if event_id in self._seen:
            return True
        self._seen[event_id] = now
        return False
