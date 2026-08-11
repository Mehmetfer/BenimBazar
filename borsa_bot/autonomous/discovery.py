"""Market discovery — BIST tradeable catalog + provider intersection; Crypto via Paribu list.

Does NOT fabricate prices for symbols without provider market data.
BIST100 = index membership (xu100 flag). Trading universe = tradeable catalog (wider).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from crypto.market import MarketType


@dataclass(frozen=True)
class DiscoveredSymbol:
    symbol: str
    market: str  # BIST | CRYPTO
    name: str = ""
    sector: str = ""
    has_market_data: bool = False
    source: str = ""
    xu100: bool = False
    tradable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_bist(*, provider_symbols: Sequence[str]) -> list[DiscoveredSymbol]:
    """Full tradeable catalog discovery; mark which have provider MD."""
    provider_set = {s.upper() for s in provider_symbols if s and s.upper() != "XU100"}
    out: list[DiscoveredSymbol] = []
    try:
        from universe.tradeable import list_tradeable

        instruments = list_tradeable()
    except Exception:  # noqa: BLE001
        instruments = []

    if instruments:
        for inst in instruments:
            # Provider may list only a subset (e.g. simulated 10). Catalog is full universe.
            has_md = inst.symbol in provider_set
            out.append(
                DiscoveredSymbol(
                    symbol=inst.symbol,
                    market=MarketType.BIST.value,
                    name=inst.name,
                    sector=inst.sector,
                    has_market_data=has_md,
                    source="catalog/bist_universe.json",
                    xu100=inst.xu100,
                    tradable=inst.tradable,
                )
            )
        catalog = {i.symbol for i in instruments}
        for s in sorted(provider_set - catalog):
            out.append(
                DiscoveredSymbol(
                    symbol=s,
                    market=MarketType.BIST.value,
                    has_market_data=True,
                    source="provider.list_symbols",
                )
            )
        return out

    # Fallback: BIST100 then provider
    try:
        from universe.bist100 import list_companies

        companies = list_companies()
    except Exception:  # noqa: BLE001
        companies = []
    if companies:
        for c in companies:
            out.append(
                DiscoveredSymbol(
                    symbol=c.ticker,
                    market=MarketType.BIST.value,
                    name=c.name,
                    sector=c.sector,
                    has_market_data=c.ticker in provider_set,
                    source="bist100_companies.json",
                    xu100=True,
                )
            )
        return out
    return [
        DiscoveredSymbol(
            symbol=s,
            market=MarketType.BIST.value,
            has_market_data=True,
            source="provider.list_symbols",
        )
        for s in sorted(provider_set)
    ]


def discover_crypto(*, provider_symbols: Sequence[str]) -> list[DiscoveredSymbol]:
    return [
        DiscoveredSymbol(
            symbol=s,
            market=MarketType.CRYPTO.value,
            has_market_data=True,
            source="paribu.list_symbols",
        )
        for s in sorted({x.upper() for x in provider_symbols if x})
    ]
