"""Crypto historical backfill — trades only (no official OHLCV endpoint)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from crypto.ohlcv import TIMEFRAME_SECONDS, TradeBarAccumulator
from crypto.providers.paribu import ParibuMarketDataProvider
from crypto.symbols import normalize_crypto_app_symbol
from data.contract import check_history


@dataclass
class CryptoBackfillResult:
    symbol: str
    timeframe: str
    bars: int
    trades: int
    ok: bool
    note: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": self.bars,
            "trades": self.trades,
            "ok": self.ok,
            "note": self.note,
            "provider": "paribu",
            "market_type": "CRYPTO",
            "official_candle_api": False,
        }


def backfill_symbol(
    provider: ParibuMarketDataProvider,
    symbol: str,
    *,
    timeframe: str = "15m",
    min_bars: int = 240,
) -> CryptoBackfillResult:
    """Pull public recent trades into accumulator and report history status.

    Official Paribu API has no candle endpoint — deep history accumulates via
    WebSocket matches over time. REST /trades only returns a short window.
    """
    if timeframe not in TIMEFRAME_SECONDS:
        return CryptoBackfillResult(symbol, timeframe, 0, 0, False, "unsupported timeframe")
    app = normalize_crypto_app_symbol(symbol)
    provider._ingest_rest_trades(app)  # noqa: SLF001 — intentional for Phase 2 backfill
    bars = provider.get_bars_tf(app, timeframe, lookback=min_bars + 10)
    trades = provider._accumulator.trade_count(app)  # noqa: SLF001
    chk = check_history(bars, min_bars=min_bars, timeframe=timeframe)
    note = chk.note
    if not chk.ok:
        note = (
            f"{chk.note} — Paribu has no official OHLCV API; "
            "history builds from public trades/WS matches (no invented bars)."
        )
    return CryptoBackfillResult(
        symbol=app,
        timeframe=timeframe,
        bars=len(bars),
        trades=trades,
        ok=chk.ok,
        note=note,
    )
