"""Market discovery — BIST catalog + provider intersection; Crypto via Paribu list.

Does NOT fabricate prices for symbols without provider market data.
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_bist(*, provider_symbols: Sequence[str]) -> list[DiscoveredSymbol]:
    """Full BIST100 catalog discovery; mark which have provider MD."""
    from universe.bist100 import list_companies

    provider_set = {s.upper() for s in provider_symbols if s and s.upper() != "XU100"}
    out: list[DiscoveredSymbol] = []
    try:
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
                )
            )
        # Include any provider-only symbols not in catalog
        catalog = {c.ticker for c in companies}
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
    # Fallback: provider list only (never invent 500 mock names)
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
