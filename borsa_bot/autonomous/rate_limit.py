"""Order rate limiter — burst protection (Master V2 §35). Fail-closed on breach."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque


@dataclass
class RateLimitResult:
    allowed: bool
    reason: str = "ok"


class OrderRateLimiter:
    def __init__(
        self,
        *,
        max_per_minute: int = 20,
        max_per_symbol_per_minute: int = 4,
        max_cancels_per_minute: int = 30,
    ) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_symbol = max_per_symbol_per_minute
        self.max_cancels = max_cancels_per_minute
        self._lock = threading.Lock()
        self._orders: Deque[float] = deque()
        self._by_symbol: dict[str, Deque[float]] = defaultdict(deque)
        self._cancels: Deque[float] = deque()

    def _prune(self, q: Deque[float], now: float) -> None:
        while q and now - q[0] > 60.0:
            q.popleft()

    def allow_order(self, symbol: str) -> RateLimitResult:
        now = time.time()
        with self._lock:
            self._prune(self._orders, now)
            sym_q = self._by_symbol[symbol.upper()]
            self._prune(sym_q, now)
            if len(self._orders) >= self.max_per_minute:
                return RateLimitResult(False, "MAX_ORDERS_PER_MINUTE")
            if len(sym_q) >= self.max_per_symbol:
                return RateLimitResult(False, "MAX_ORDERS_PER_SYMBOL")
            self._orders.append(now)
            sym_q.append(now)
            return RateLimitResult(True)

    def allow_cancel(self) -> RateLimitResult:
        now = time.time()
        with self._lock:
            self._prune(self._cancels, now)
            if len(self._cancels) >= self.max_cancels:
                return RateLimitResult(False, "MAX_CANCELS_PER_MINUTE")
            self._cancels.append(now)
            return RateLimitResult(True)


order_rate_limiter = OrderRateLimiter()
