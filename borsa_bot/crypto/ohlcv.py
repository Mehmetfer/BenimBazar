"""Build canonical OHLCV bars from Paribu public trades (no candle API exists)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from config.models import Bar
from crypto.rest import RawTrade
from data.contract import EnvironmentOrigin, stamp_bar_defaults, validate_canonical_bar
from data.integrity import DataSourceKind


TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def floor_ts(ts: datetime, timeframe: str) -> datetime:
    sec = TIMEFRAME_SECONDS[timeframe]
    epoch = int(ts.astimezone(timezone.utc).timestamp())
    floored = epoch - (epoch % sec)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def aggregate_trades_to_bars(
    trades: Iterable[RawTrade],
    *,
    symbol: str,
    timeframe: str = "15m",
    provider: str = "paribu",
) -> list[Bar]:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"unsupported timeframe {timeframe}")
    buckets: dict[datetime, list[RawTrade]] = defaultdict(list)
    for tr in trades:
        if tr.price <= 0 or tr.amount < 0:
            continue
        buckets[floor_ts(tr.time, timeframe)].append(tr)

    bars: list[Bar] = []
    for ts in sorted(buckets.keys()):
        chunk = sorted(buckets[ts], key=lambda x: x.time)
        prices = [t.price for t in chunk]
        vol = sum(t.amount for t in chunk)
        o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
        bar = Bar(
            ts=ts,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=vol,
            trades=len(chunk),
            data_source_kind=DataSourceKind.LIVE.value,
            symbol=symbol,
            timeframe=timeframe,
            provider=provider,
        )
        stamp_bar_defaults(bar, provider=provider, origin=EnvironmentOrigin.LIVE, symbol=symbol, timeframe=timeframe)
        # origin expects EnvironmentOrigin — stamp_bar_defaults may accept string; check
        chk = validate_canonical_bar(bar)
        if chk.ok:
            bars.append(bar)
    return bars


class TradeBarAccumulator:
    """In-memory trade → OHLCV store for WS + REST trades."""

    def __init__(self) -> None:
        self._trades: dict[str, list[RawTrade]] = defaultdict(list)
        self._max_trades_per_symbol = 50_000

    def add_trade(self, app_symbol: str, trade: RawTrade) -> None:
        buf = self._trades[app_symbol]
        buf.append(trade)
        if len(buf) > self._max_trades_per_symbol:
            self._trades[app_symbol] = buf[-self._max_trades_per_symbol :]

    def add_trades(self, app_symbol: str, trades: Iterable[RawTrade]) -> None:
        for t in trades:
            self.add_trade(app_symbol, t)

    def bars(self, app_symbol: str, timeframe: str = "15m", lookback: int = 240) -> list[Bar]:
        trades = self._trades.get(app_symbol) or []
        all_bars = aggregate_trades_to_bars(trades, symbol=app_symbol, timeframe=timeframe)
        return all_bars[-lookback:]

    def trade_count(self, app_symbol: str) -> int:
        return len(self._trades.get(app_symbol) or [])
