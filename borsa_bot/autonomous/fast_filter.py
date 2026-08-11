"""Fast filter — cheap ranking before deep analysis.

Never collapses universe to a hardcoded 3–5 by policy; only ranks available MD symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from autonomous.discovery import DiscoveredSymbol
from data.providers import MarketDataProvider


@dataclass
class FastFilterResult:
    universe: int
    with_market_data: int
    fast_filter: int
    candidates: list[str]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe,
            "with_market_data": self.with_market_data,
            "fast_filter": self.fast_filter,
            "candidates": list(self.candidates),
            "stats": self.stats,
        }


def fast_filter_bist(
    discovered: Sequence[DiscoveredSymbol],
    provider: MarketDataProvider,
    *,
    favorites: set[str] | None = None,
    max_deep: int = 40,
) -> FastFilterResult:
    """Rank symbols that have provider data; favorites always included first."""
    favs = {f.upper() for f in (favorites or set())}
    tradeable = [d for d in discovered if d.has_market_data]
    scored: list[tuple[float, str]] = []
    for d in tradeable:
        sym = d.symbol
        score = 0.0
        if sym in favs:
            score += 1000.0
        try:
            q = provider.get_quote(sym)
            bars = provider.get_bars(sym, 40)
            vol = float(q.volume or 0)
            spread = float(q.spread_pct or 99)
            score += min(vol / 1_000_000.0, 50.0)  # liquidity proxy
            score += max(0.0, 10.0 - spread * 10.0)
            if len(bars) >= 20 and bars[-20].close > 0:
                mom = (bars[-1].close / bars[-20].close - 1.0) * 100.0
                score += abs(mom) * 0.5  # activity, not direction bias alone
            if q.price and q.price > 0:
                score += 1.0
        except Exception:  # noqa: BLE001
            continue
        scored.append((score, sym))
    scored.sort(key=lambda x: (-x[0], x[1]))
    # Keep at least all favorites with data; cap deep analysis
    deep_n = max(5, min(int(max_deep), len(scored)))
    # Prefer not collapsing below min(10, available) when data exists
    if len(scored) >= 10:
        deep_n = max(deep_n, min(10, len(scored)))
    candidates = [s for _, s in scored[:deep_n]]
    # Ensure favorites present
    for f in favs:
        if f in {d.symbol for d in tradeable} and f not in candidates:
            candidates.insert(0, f)
    return FastFilterResult(
        universe=len(discovered),
        with_market_data=len(tradeable),
        fast_filter=len(candidates),
        candidates=candidates,
        stats={
            "favorites_boosted": sorted(favs & {d.symbol for d in tradeable}),
            "max_deep": max_deep,
            "note": "Symbols without provider market data are excluded from deep analysis (no fabricated prices).",
        },
    )
