from __future__ import annotations

from config.models import IndicatorSet, MarketRegime, SignalAction
from config.settings import settings
from strategy.modules import ensemble_votes
from strategy.regime import trend_label


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_buy(ind: IndicatorSet, close: float, volume: float, regime: MarketRegime, index_bullish: bool) -> float:
    # Trend 25
    trend = 0.0
    if ind.ema9 > ind.ema21 > ind.ema50:
        trend += 15
    if close > ind.ema200:
        trend += 10
    # Momentum 15
    mom = _clamp((ind.momentum10 + 3) / 6 * 15)
    # Volume 15
    vol_ratio = volume / ind.vol_sma20 if ind.vol_sma20 else 1
    vol = _clamp((vol_ratio - 0.8) / 0.8 * 15)
    # RSI 10 (prefer 40-60 rising zone, penalize extremes for trend buys)
    if 40 <= ind.rsi14 <= 60:
        rsi_s = 10
    elif 30 <= ind.rsi14 < 40 or 60 < ind.rsi14 <= 68:
        rsi_s = 6
    else:
        rsi_s = 2
    # MACD 10
    macd_s = 10 if ind.macd_hist > 0 and ind.macd > ind.macd_signal else 3
    # Volatility 10 (ATR not too wild vs price)
    atr_pct = ind.atr14 / close * 100 if close else 5
    vola = 10 if 0.5 <= atr_pct <= 3.5 else 4
    # Index 10
    idx = 10 if index_bullish else 2
    # News/fundamental placeholder 5 (neutral until wired)
    news = 3
    total = trend + mom + vol + rsi_s + macd_s + vola + idx + news
    # Regime dampener
    if regime == MarketRegime.STRONG_BEAR:
        total *= 0.45
    elif regime == MarketRegime.BEAR:
        total *= 0.65
    elif regime == MarketRegime.SIDEWAYS:
        total *= 0.9
    return round(_clamp(total), 1)


def score_sell(ind: IndicatorSet, close: float, volume: float, owned: bool) -> float:
    if not owned:
        # Still compute pressure but keep lower unless extreme
        base_owned = False
    else:
        base_owned = True
    trend = 20 if ind.ema9 < ind.ema21 < ind.ema50 else 5
    mom = _clamp((-ind.momentum10 + 3) / 6 * 15)
    vol_ratio = volume / ind.vol_sma20 if ind.vol_sma20 else 1
    vol = _clamp((vol_ratio - 0.8) / 0.8 * 10)
    rsi_s = 15 if ind.rsi14 >= 70 else (8 if ind.rsi14 >= 60 else 3)
    macd_s = 15 if ind.macd_hist < 0 and ind.macd < ind.macd_signal else 4
    bb = 15 if close >= ind.bb_upper else 4
    stoch = 10 if ind.stoch_k >= 80 and ind.stoch_k < ind.stoch_d else 3
    total = trend + mom + vol + rsi_s + macd_s + bb + stoch
    if not base_owned:
        total *= 0.55
    return round(_clamp(total), 1)


def decide_action(
    buy_score: float,
    sell_score: float,
    owned: bool,
    regime: MarketRegime,
) -> SignalAction:
    if owned and sell_score >= settings.sell_score_threshold:
        return SignalAction.SAT
    if (not owned) and buy_score >= settings.buy_score_threshold:
        if regime == MarketRegime.STRONG_BEAR:
            return SignalAction.BEKLE  # capital preservation
        return SignalAction.AL
    if (not owned) and buy_score < 55:
        return SignalAction.ALMA
    return SignalAction.BEKLE


def build_explanation(
    action: SignalAction,
    buy_score: float,
    sell_score: float,
    ind: IndicatorSet,
    votes: dict[str, str],
    regime: MarketRegime,
) -> str:
    vote_txt = ", ".join(f"{k}:{v}" for k, v in votes.items())
    return (
        f"Rejim={regime.value}; BUY={buy_score:.0f} SELL={sell_score:.0f}; "
        f"trend={trend_label(ind)}; RSI={ind.rsi14:.1f}; ADX={ind.adx14:.1f}; "
        f"ensemble=[{vote_txt}]; karar={action.value}"
    )
