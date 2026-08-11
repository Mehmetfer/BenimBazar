"""AI / LLM cost governor — fall back to quant engine; never mock data."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class CostDecision:
    allowed: bool
    reason: str
    mode: str  # QUANT | LLM | BLOCKED


class AICostGovernor:
    def __init__(self, *, max_calls_per_minute: int = 30, max_calls_per_hour: int = 400) -> None:
        self.max_per_min = max_calls_per_minute
        self.max_per_hour = max_calls_per_hour
        self._lock = threading.Lock()
        self._calls: list[float] = []

    def allow(self, *, want_llm: bool = False) -> CostDecision:
        now = time.time()
        with self._lock:
            self._calls = [t for t in self._calls if now - t < 3600]
            hour_n = len(self._calls)
            min_n = sum(1 for t in self._calls if now - t < 60)
            if hour_n >= self.max_per_hour or min_n >= self.max_per_min:
                return CostDecision(False, "AI_COST_LIMIT", "BLOCKED")
            self._calls.append(now)
        if want_llm:
            # LLM not wired — always quant fallback (no fabricated MD)
            return CostDecision(True, "LLM_DISABLED_USE_QUANT", "QUANT")
        return CostDecision(True, "ok", "QUANT")


ai_cost_governor = AICostGovernor()
