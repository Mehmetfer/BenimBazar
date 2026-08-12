"""Crypto historical backfill — public OHLCV when available; Paribu trades otherwise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto.ohlcv import TIMEFRAME_SECONDS
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
    provider: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": self.bars,
            "trades": self.trades,
            "ok": self.ok,
            "note": self.note,
            "provider": self.provider,
            "market_type": "CRYPTO",
            "official_candle_api": self.provider not in {"paribu", ""},
        }


def backfill_symbol(
    provider: Any,
    symbol: str,
    *,
    timeframe: str = "15m",
    min_bars: int = 240,
) -> CryptoBackfillResult:
    """Fetch history for charting/TA.

    Public CEX (OKX/Gate/Kraken): native candle API.
    Paribu: accumulate from public trades/WS (no official candle endpoint).
    """
    pid = str(getattr(provider, "provider_id", "") or type(provider).__name__)
    if timeframe not in TIMEFRAME_SECONDS and timeframe not in {
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "1d",
        "1w",
    }:
        return CryptoBackfillResult(symbol, timeframe, 0, 0, False, "unsupported timeframe", provider=pid)
    app = normalize_crypto_app_symbol(symbol)

    # Paribu-specific trade ingest when available
    ingest = getattr(provider, "_ingest_rest_trades", None)
    if callable(ingest):
        try:
            ingest(app)
        except Exception:  # noqa: BLE001
            pass

    try:
        bars = provider.get_bars_tf(app, timeframe, lookback=min_bars + 10)
    except Exception as exc:  # noqa: BLE001
        return CryptoBackfillResult(app, timeframe, 0, 0, False, f"NO_MARKET_DATA:{exc}", provider=pid)

    trades = 0
    acc = getattr(provider, "_accumulator", None)
    if acc is not None and hasattr(acc, "trade_count"):
        try:
            trades = int(acc.trade_count(app))
        except Exception:  # noqa: BLE001
            trades = 0

    chk = check_history(bars, min_bars=min_bars, timeframe=timeframe)
    note = chk.note
    if not chk.ok and "paribu" in pid.lower():
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
        provider=pid,
    )
