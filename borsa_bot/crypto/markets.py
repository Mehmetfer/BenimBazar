"""Crypto market catalog — discovery metadata from Paribu ticker (no hardcoded coins)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from crypto.rest import RawTicker
from crypto.symbols import parse_crypto_symbol, to_display_symbol


@dataclass
class CryptoMarketInfo:
    canonical_symbol: str  # BTC_TL
    provider_symbol: str  # btc_tl
    display: str  # BTC/TL
    base_asset: str
    quote_asset: str
    market_id: str
    status: str = "ACTIVE"
    last: float | None = None
    volume: float | None = None
    pair_volume: float | None = None
    # Official ticker does not expose precision / min_amount — leave UNKNOWN
    precision: str = "UNKNOWN"
    min_amount: str = "UNKNOWN"
    min_cost: str = "UNKNOWN"
    price_increment: str = "UNKNOWN"
    amount_increment: str = "UNKNOWN"
    provider: str = "paribu"
    market_type: str = "CRYPTO"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def market_info_from_ticker(raw: RawTicker) -> CryptoMarketInfo | None:
    ref = parse_crypto_symbol(raw.market)
    if ref is None:
        return None
    return CryptoMarketInfo(
        canonical_symbol=ref.app_symbol,
        provider_symbol=raw.market,
        display=to_display_symbol(ref.app_symbol),
        base_asset=ref.base,
        quote_asset=ref.quote,
        market_id=raw.market,
        status="ACTIVE" if raw.last > 0 else "UNAVAILABLE",
        last=float(raw.last),
        volume=float(raw.volume),
        pair_volume=float(raw.pair_volume),
        extra={
            "high_24h": raw.high,
            "low_24h": raw.low,
            "change_pct": raw.percentage,
        },
    )


def build_market_catalog(tickers: list[RawTicker]) -> list[CryptoMarketInfo]:
    out: list[CryptoMarketInfo] = []
    seen: set[str] = set()
    for t in tickers:
        info = market_info_from_ticker(t)
        if info is None or info.canonical_symbol in seen:
            continue
        seen.add(info.canonical_symbol)
        out.append(info)
    out.sort(key=lambda m: m.canonical_symbol)
    return out
