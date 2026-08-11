"""Minimal OHLCV storage abstraction — no new DB engine.

In-memory default. Future BIST adapter may persist via same interface.
Never invents bars. Stale/empty → caller must fail closed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from config.models import Bar
from data.contract import (
    BASE_TIMEFRAME,
    REQUIRED_HISTORY_BARS_15M,
    check_history,
    normalize_app_symbol,
    sort_bars_safe,
)


class OhlcvStore(Protocol):
    def get_bars(self, symbol: str, timeframe: str = BASE_TIMEFRAME, lookback: int = 240) -> list[Bar]: ...
    def save_bars(self, symbol: str, bars: list[Bar], timeframe: str = BASE_TIMEFRAME) -> int: ...
    def latest_bar(self, symbol: str, timeframe: str = BASE_TIMEFRAME) -> Bar | None: ...
    def latest_timestamp(self, symbol: str, timeframe: str = BASE_TIMEFRAME) -> datetime | None: ...
    def has_bars(self, symbol: str, timeframe: str = BASE_TIMEFRAME, min_count: int = 1) -> bool: ...


class InMemoryOhlcvStore:
    """Process-local bar store. Duplicate-safe via sort_bars_safe."""

    def __init__(self) -> None:
        self._bars: dict[tuple[str, str], list[Bar]] = {}

    def get_bars(self, symbol: str, timeframe: str = BASE_TIMEFRAME, lookback: int = 240) -> list[Bar]:
        key = (normalize_app_symbol(symbol), timeframe)
        bars = self._bars.get(key, [])
        return list(bars[-lookback:])

    def save_bars(self, symbol: str, bars: list[Bar], timeframe: str = BASE_TIMEFRAME) -> int:
        sym = normalize_app_symbol(symbol)
        key = (sym, timeframe)
        existing = list(self._bars.get(key, []))
        existing.extend(bars)
        cleaned = sort_bars_safe(existing)
        self._bars[key] = cleaned
        return len(cleaned)

    def latest_bar(self, symbol: str, timeframe: str = BASE_TIMEFRAME) -> Bar | None:
        bars = self.get_bars(symbol, timeframe, lookback=1)
        return bars[-1] if bars else None

    def latest_timestamp(self, symbol: str, timeframe: str = BASE_TIMEFRAME) -> datetime | None:
        b = self.latest_bar(symbol, timeframe)
        return b.ts if b else None

    def has_bars(
        self,
        symbol: str,
        timeframe: str = BASE_TIMEFRAME,
        min_count: int = 1,
    ) -> bool:
        return len(self.get_bars(symbol, timeframe, lookback=max(min_count, 1))) >= min_count

    def history_ok(
        self,
        symbol: str,
        timeframe: str = BASE_TIMEFRAME,
        min_bars: int = REQUIRED_HISTORY_BARS_15M,
    ) -> bool:
        return check_history(self.get_bars(symbol, timeframe, lookback=min_bars + 10), min_bars=min_bars).ok
