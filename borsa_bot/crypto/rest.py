"""Official Paribu REST market-data helpers (docs.paribu.com)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crypto.http_client import ParibuHTTPClient


@dataclass(frozen=True)
class RawTicker:
    market: str  # provider wire e.g. btc_tl
    last: float
    low: float
    high: float
    first: float
    volume: float
    pair_volume: float
    change: float
    percentage: float
    average: float


@dataclass(frozen=True)
class RawOrderBook:
    market: str
    timestamp: datetime  # UTC
    bid: float
    ask: float
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


@dataclass(frozen=True)
class RawTrade:
    price: float
    amount: float
    time: datetime
    side: str


def _f(v: Any) -> float:
    return float(v)


def parse_ticker_row(row: dict[str, Any]) -> RawTicker:
    return RawTicker(
        market=str(row.get("market") or "").strip().lower(),
        last=_f(row["last"]),
        low=_f(row["low"]),
        high=_f(row["high"]),
        first=_f(row["first"]),
        volume=_f(row["volume"]),
        pair_volume=_f(row.get("pair_volume") or 0),
        change=_f(row.get("change") or 0),
        percentage=_f(row.get("percentage") or 0),
        average=_f(row.get("average") or 0),
    )


def fetch_tickers(client: ParibuHTTPClient, market: str | None = None, *, cache_ttl_sec: float = 2.0) -> list[RawTicker]:
    params = {"market": market} if market else None
    resp = client.get_json("/market/ticker", params, cache_ttl_sec=cache_ttl_sec, weight=1)
    data = resp.data
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("ticker payload not a list")
    out: list[RawTicker] = []
    for row in data:
        if not isinstance(row, dict) or not row.get("market"):
            continue
        try:
            out.append(parse_ticker_row(row))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_orderbook(
    client: ParibuHTTPClient,
    market: str,
    *,
    depth: int = 5,
    cache_ttl_sec: float = 1.0,
) -> RawOrderBook:
    market = market.strip().lower()
    resp = client.get_json(
        "/orderbook",
        {"market": market, "depth": max(1, min(20, int(depth)))},
        cache_ttl_sec=cache_ttl_sec,
        weight=2,
    )
    data = resp.data
    if not isinstance(data, dict):
        raise ValueError("orderbook payload invalid")
    bids_raw = data.get("bids") or []
    asks_raw = data.get("asks") or []
    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    for level in bids_raw:
        if isinstance(level, (list, tuple)) and len(level) >= 2:
            bids.append((_f(level[0]), _f(level[1])))
    for level in asks_raw:
        if isinstance(level, (list, tuple)) and len(level) >= 2:
            asks.append((_f(level[0]), _f(level[1])))
    if not bids or not asks:
        raise ValueError("orderbook missing bid/ask")
    ts_raw = data.get("timestamp")
    if ts_raw is None:
        ts = datetime.now(timezone.utc)
    else:
        # docs: unix timestamp (seconds observed in live probe)
        ts_f = float(ts_raw)
        if ts_f > 1e12:
            ts_f /= 1000.0
        ts = datetime.fromtimestamp(ts_f, tz=timezone.utc)
    return RawOrderBook(
        market=market,
        timestamp=ts,
        bid=bids[0][0],
        ask=asks[0][0],
        bids=bids,
        asks=asks,
    )


def fetch_recent_trades(
    client: ParibuHTTPClient,
    market: str,
    *,
    limit: int = 5,
    cache_ttl_sec: float = 1.0,
) -> list[RawTrade]:
    market = market.strip().lower()
    # Public API: limit must not exceed 20 (HTTP 400 / code 4001 verified live).
    limit = max(1, min(20, int(limit)))
    resp = client.get_json(
        "/trades",
        {"market": market, "limit": limit},
        cache_ttl_sec=cache_ttl_sec,
        weight=1,
    )
    data = resp.data
    if not isinstance(data, list):
        raise ValueError("trades payload invalid")
    out: list[RawTrade] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        try:
            t_raw = str(row["time"])
            # nanoseconds sometimes present — normalize to fromisoformat-friendly
            if t_raw.endswith("Z"):
                t_raw = t_raw[:-1] + "+00:00"
            # trim >6 fractional digits
            if "." in t_raw:
                head, frac = t_raw.split(".", 1)
                sign = ""
                if "+" in frac:
                    frac, sign = frac.split("+", 1)
                    sign = "+" + sign
                elif "-" in frac[1:]:
                    # timezone -HH:MM after fractional
                    idx = frac.find("-")
                    if idx > 0:
                        sign = frac[idx:]
                        frac = frac[:idx]
                frac = (frac + "000000")[:6]
                t_raw = f"{head}.{frac}{sign}"
            ts = datetime.fromisoformat(t_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            out.append(
                RawTrade(
                    price=_f(row["price"]),
                    amount=_f(row["amount"]),
                    time=ts,
                    side=str(row.get("trade") or "").lower(),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out
