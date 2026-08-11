from __future__ import annotations

from config.models import IndicatorSet, MarketRegime
from indicators.engine import compute_indicators
from data.providers import MarketDataProvider


def detect_regime(provider: MarketDataProvider) -> MarketRegime:
    bars = provider.get_bars("XU100", 220)
    ind = compute_indicators(bars)
    if ind is None:
        return MarketRegime.NEUTRAL
    slope = (ind.ema21 - ind.ema50) / ind.ema50 * 100 if ind.ema50 else 0
    strength = ind.adx14
    above200 = ind.ema21 > ind.ema200
    vol_ratio = 1.0
    quote = provider.get_quote("XU100")
    if ind.vol_sma20:
        vol_ratio = quote.volume / ind.vol_sma20
    # Breadth proxy: share of universe above EMA50
    bullish = 0
    total = 0
    for sym in provider.list_symbols():
        b = provider.get_bars(sym, 80)
        if len(b) < 60:
            continue
        closes = [x.close for x in b]
        ema50 = sum(closes[-50:]) / 50
        total += 1
        if closes[-1] > ema50:
            bullish += 1
    breadth = bullish / total if total else 0.5

    if above200 and slope > 1.2 and strength >= 25 and ind.rsi14 >= 55 and breadth >= 0.6:
        return MarketRegime.STRONG_BULL
    if above200 and slope > 0.2 and ind.rsi14 >= 48 and breadth >= 0.5:
        return MarketRegime.BULL
    if (not above200) and slope < -1.2 and strength >= 25 and ind.rsi14 <= 45 and breadth <= 0.4:
        return MarketRegime.STRONG_BEAR
    if (not above200) and slope < -0.2 and ind.rsi14 <= 52 and breadth <= 0.45:
        return MarketRegime.BEAR
    _ = vol_ratio  # reserved for volatility regime overlays
    return MarketRegime.NEUTRAL


def trend_label(ind: IndicatorSet) -> str:
    if ind.ema9 > ind.ema21 > ind.ema50 > ind.ema200:
        return "BULL"
    if ind.ema9 < ind.ema21 < ind.ema50 < ind.ema200:
        return "BEAR"
    return "NEUTRAL"


def regime_buy_threshold_boost(regime: MarketRegime) -> float:
    if regime == MarketRegime.STRONG_BEAR:
        return 12.0
    if regime == MarketRegime.BEAR:
        return 6.0
    if regime == MarketRegime.NEUTRAL:
        return 3.0
    if regime == MarketRegime.STRONG_BULL:
        return -3.0
    return 0.0
