"""In-process scheduler guard — prevent overlapping autonomous cycles."""

from __future__ import annotations

import threading
import time
from typing import Any


class CycleSchedulerGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[str, float] = {}
        self._last_finished: dict[str, float] = {}

    def try_begin(
        self,
        market: str,
        *,
        min_interval_sec: float = 30.0,
        force: bool = False,
    ) -> tuple[bool, str]:
        now = time.time()
        with self._lock:
            if market in self._running and not force:
                return False, "CYCLE_ALREADY_RUNNING"
            last = self._last_finished.get(market, 0.0)
            if not force and now - last < min_interval_sec:
                return False, f"CYCLE_COOLDOWN:{int(min_interval_sec - (now - last))}s"
            self._running[market] = now
            return True, "ok"

    def end(self, market: str, meta: dict[str, Any] | None = None) -> None:
        del meta  # reserved
        with self._lock:
            self._running.pop(market, None)
            self._last_finished[market] = time.time()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": dict(self._running),
                "last_finished": dict(self._last_finished),
            }


scheduler_guard = CycleSchedulerGuard()
