from __future__ import annotations

from config.models import IndicatorSet, MarketRegime, QuoteSnapshot
from data.providers import MarketDataProvider
from indicators.engine import compute_indicators


def sector_relative_strength(
    provider: MarketDataProvider,
    symbol: str,
    sector: str,
    lookback: int = 20,
) -> tuple[float, float, list[str]]:
    """RS vs sector peers and vs XU100. Returns (rs_score 0-100, sector_score, notes)."""
    notes: list[str] = []
    sym_bars = provider.get_bars(symbol, lookback + 5)
    if len(sym_bars) < lookback + 1:
        return 50.0, 50.0, ["rs_insufficient"]
    sym_ret = sym_bars[-1].close / sym_bars[-lookback].close - 1
    peers = []
    for s in provider.list_symbols():
        q = provider.get_quote(s)
        if q.sector != sector or s == symbol:
            continue
        pb = provider.get_bars(s, lookback + 5)
        if len(pb) < lookback + 1:
            continue
        peers.append(pb[-1].close / pb[-lookback].close - 1)
    sector_ret = sum(peers) / len(peers) if peers else 0.0
    xu = provider.get_bars("XU100", lookback + 5)
    xu_ret = (xu[-1].close / xu[-lookback].close - 1) if len(xu) >= lookback + 1 else 0.0

    # Sector strength vs index
    sector_score = 50 + (sector_ret - xu_ret) * 200
    sector_score = max(0.0, min(100.0, sector_score))
    # Stock vs sector
    rs = 50 + (sym_ret - sector_ret) * 250
    rs = max(0.0, min(100.0, rs))
    if sector_score >= 60 and rs >= 55:
        notes.append("strong_sector_strong_stock")
    elif sector_score < 40:
        notes.append("weak_sector_filter")
    return rs, sector_score, notes


def liquidity_score(quote: QuoteSnapshot, ind: IndicatorSet) -> tuple[float, list[str]]:
    notes = []
    score = 70.0
    if quote.spread_pct > 0.5:
        score -= 25
        notes.append("wide_spread")
    elif quote.spread_pct < 0.15:
        score += 10
        notes.append("tight_spread")
    if ind.vol_sma20 and quote.volume < ind.vol_sma20 * 0.4:
        score -= 20
        notes.append("low_liquidity")
    if quote.trades < 200:
        score -= 10
        notes.append("thin_trade_count")
    return max(0.0, min(100.0, score)), notes
