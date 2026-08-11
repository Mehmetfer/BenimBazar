"""Historical backfill abstraction — idempotent, source-aware, no mock padding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from config.models import Bar
from data.contract import (
    BASE_TIMEFRAME,
    REQUIRED_HISTORY_BARS_15M,
    DataQuality,
    check_history,
    normalize_app_symbol,
    sort_bars_safe,
    stamp_bar_defaults,
    EnvironmentOrigin,
)
from data.storage import InMemoryOhlcvStore, OhlcvStore


@dataclass(frozen=True)
class BackfillResult:
    symbol: str
    timeframe: str
    bars_written: int
    total_bars: int
    quality: str
    ok: bool
    note: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars_written": self.bars_written,
            "total_bars": self.total_bars,
            "quality": self.quality,
            "ok": self.ok,
            "note": self.note,
        }


class HistoricalBackfill(Protocol):
    def backfill(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> BackfillResult: ...


class NoOpBackfill:
    """Default until real BIST provider is connected — returns INSUFFICIENT_HISTORY."""

    def __init__(self, store: OhlcvStore | None = None) -> None:
        self.store = store or InMemoryOhlcvStore()

    def backfill(
        self,
        symbol: str,
        timeframe: str = BASE_TIMEFRAME,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BackfillResult:
        sym = normalize_app_symbol(symbol)
        existing = self.store.get_bars(sym, timeframe, lookback=REQUIRED_HISTORY_BARS_15M + 50)
        chk = check_history(existing, min_bars=REQUIRED_HISTORY_BARS_15M, timeframe=timeframe)
        return BackfillResult(
            symbol=sym,
            timeframe=timeframe,
            bars_written=0,
            total_bars=len(existing),
            quality=chk.quality.value,
            ok=chk.ok,
            note=(
                "NO_OP_BACKFILL — real provider not connected. "
                "Do not pad with mock/random/placeholder."
                if not chk.ok
                else "existing history sufficient"
            ),
        )


def apply_backfill_bars(
    store: OhlcvStore,
    symbol: str,
    bars: list[Bar],
    *,
    timeframe: str = BASE_TIMEFRAME,
    provider: str,
    origin: EnvironmentOrigin = EnvironmentOrigin.LIVE,
) -> BackfillResult:
    """Idempotent write of provider bars into store (dedupe + sort)."""
    sym = normalize_app_symbol(symbol)
    stamped = [
        stamp_bar_defaults(b, provider=provider, origin=origin, symbol=sym, timeframe=timeframe)
        for b in bars
    ]
    cleaned = sort_bars_safe(stamped)
    total = store.save_bars(sym, cleaned, timeframe=timeframe)
    chk = check_history(store.get_bars(sym, timeframe, lookback=total), min_bars=REQUIRED_HISTORY_BARS_15M)
    return BackfillResult(
        symbol=sym,
        timeframe=timeframe,
        bars_written=len(cleaned),
        total_bars=total,
        quality=chk.quality.value,
        ok=chk.ok,
        note=chk.note,
    )
