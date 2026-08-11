from __future__ import annotations

from config.models import IndicatorSet, MarketRegime
from strategy.ranking import REGIME_STRATEGY_WEIGHTS, vote_pullback


def vote_trend_following(ind: IndicatorSet) -> str:
    if ind.ema9 > ind.ema21 > ind.ema50 and ind.adx14 >= 20:
        return "AL"
    if ind.ema9 < ind.ema21 < ind.ema50 and ind.adx14 >= 20:
        return "SAT"
    return "BEKLE"


def vote_ema_crossover(ind: IndicatorSet) -> str:
    if ind.ema9 > ind.ema21 and ind.ema21 > ind.ema50:
        return "AL"
    if ind.ema9 < ind.ema21 and ind.ema21 < ind.ema50:
        return "SAT"
    return "BEKLE"


def vote_momentum(ind: IndicatorSet) -> str:
    if ind.momentum10 > 1.5 and ind.rsi14 < 70:
        return "AL"
    if ind.momentum10 < -1.5 and ind.rsi14 > 30:
        return "SAT"
    return "BEKLE"


def vote_mean_reversion(ind: IndicatorSet) -> str:
    if ind.rsi14 < 30 and ind.stoch_k < 20:
        return "AL"
    if ind.rsi14 > 70 and ind.stoch_k > 80:
        return "SAT"
    return "BEKLE"


def vote_breakout(ind: IndicatorSet, close: float) -> str:
    if close > ind.bb_upper and ind.vol_sma20 > 0:
        return "AL"
    if close < ind.bb_lower:
        return "SAT"
    return "BEKLE"


def vote_volume_breakout(ind: IndicatorSet, volume: float, close: float) -> str:
    if volume > ind.vol_sma20 * 1.4 and close > ind.vwap and ind.momentum10 > 0:
        return "AL"
    if volume > ind.vol_sma20 * 1.4 and close < ind.vwap and ind.momentum10 < 0:
        return "SAT"
    return "BEKLE"


def ensemble_votes(ind: IndicatorSet, close: float, volume: float) -> dict[str, str]:
    return {
        "trend_following": vote_trend_following(ind),
        "ema_crossover": vote_ema_crossover(ind),
        "momentum": vote_momentum(ind),
        "mean_reversion": vote_mean_reversion(ind),
        "breakout": vote_breakout(ind, close),
        "volume_breakout": vote_volume_breakout(ind, volume, close),
        "pullback": vote_pullback(ind, close),
    }


def regime_weights(regime: MarketRegime) -> dict[str, float]:
    return dict(REGIME_STRATEGY_WEIGHTS.get(regime, REGIME_STRATEGY_WEIGHTS[MarketRegime.NEUTRAL]))


def weighted_ensemble_bias(votes: dict[str, str], weights: dict[str, float]) -> float:
    """Positive => buy bias, negative => sell. Not a trade permission."""
    score = 0.0
    for name, vote in votes.items():
        w = weights.get(name, 0.5)
        if vote == "AL":
            score += w
        elif vote == "SAT":
            score -= w
    return round(score, 3)
