"""Crypto chart adapter — bars → UI series (no BIST chart copy)."""

from __future__ import annotations

from typing import Any, Sequence

from config.models import Bar
from crypto.ohlcv import TIMEFRAME_SECONDS

SUPPORTED_TF = ("15m", "1h", "4h", "1d")


def normalize_timeframe(tf: str) -> str:
    t = (tf or "15m").strip().lower()
    aliases = {"15": "15m", "60": "1h", "240": "4h", "d": "1d", "1d": "1d", "day": "1d"}
    t = aliases.get(t, t)
    if t not in TIMEFRAME_SECONDS:
        raise ValueError(f"unsupported timeframe {tf}")
    return t


def bars_to_chart(bars: Sequence[Bar], *, symbol: str, timeframe: str) -> dict[str, Any]:
    """Market-specific chart payload for the crypto UI sparkline/OHLC view."""
    tf = normalize_timeframe(timeframe)
    candles = []
    for b in bars:
        candles.append(
            {
                "t": b.ts.isoformat() if b.ts else None,
                "o": b.open,
                "h": b.high,
                "l": b.low,
                "c": b.close,
                "v": b.volume,
            }
        )
    closes = [c["c"] for c in candles if c.get("c") is not None]
    return {
        "market_type": "CRYPTO",
        "symbol": symbol,
        "timeframe": tf,
        "supported_timeframes": list(SUPPORTED_TF),
        "candles": candles,
        "closes": closes,
        "count": len(candles),
        "source": "paribu_trade_aggregation",
        "note": "Paribu has no official OHLCV endpoint — bars from public trades",
        "paper_only": True,
    }
