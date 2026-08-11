from __future__ import annotations

from config.models import IndicatorSet, MarketRegime
from indicators.engine import compute_indicators
from data.providers import MarketDataProvider


def detect_regime(provider: MarketDataProvider) -> MarketRegime:
    bars = provider.get_bars("XU100", 220)
    ind = compute_indicators(bars)
    if ind is None:
        return MarketRegime.SIDEWAYS
    slope = (ind.ema21 - ind.ema50) / ind.ema50 * 100 if ind.ema50 else 0
    strength = ind.adx14
    above200 = ind.ema21 > ind.ema200
    if above200 and slope > 1.2 and strength >= 25 and ind.rsi14 >= 55:
        return MarketRegime.STRONG_BULL
    if above200 and slope > 0.2 and ind.rsi14 >= 48:
        return MarketRegime.BULL
    if (not above200) and slope < -1.2 and strength >= 25 and ind.rsi14 <= 45:
        return MarketRegime.STRONG_BEAR
    if (not above200) and slope < -0.2 and ind.rsi14 <= 52:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS


def trend_label(ind: IndicatorSet) -> str:
    if ind.ema9 > ind.ema21 > ind.ema50 > ind.ema200:
        return "BULL"
    if ind.ema9 < ind.ema21 < ind.ema50 < ind.ema200:
        return "BEAR"
    return "SIDEWAYS"
