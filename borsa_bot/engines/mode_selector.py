from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.models import MarketRegime
from indicators.engine import compute_indicators
from data.providers import MarketDataProvider


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class TrendState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"


class Horizon(str, Enum):
    LONG_TERM = "LONG_TERM"
    SWING = "SWING"
    DAY_TRADING = "DAY_TRADING"
    NO_TRADE = "NO_TRADE"


@dataclass
class ModeDecision:
    market: MarketRegime
    volatility: VolatilityRegime
    trend: TrendState
    priorities: list[Horizon]
    primary: Horizon
    reason: str
    cash_bias: float  # 0-1 extra cash preference


def classify_volatility(atr_pct: float) -> VolatilityRegime:
    if atr_pct >= 5.0:
        return VolatilityRegime.EXTREME
    if atr_pct >= 3.5:
        return VolatilityRegime.HIGH
    if atr_pct <= 1.2:
        return VolatilityRegime.LOW
    return VolatilityRegime.NORMAL


def classify_trend(ind) -> TrendState:
    if ind is None:
        return TrendState.SIDEWAYS
    if ind.ema21 > ind.ema50 > ind.ema200 and ind.structure == "HH_HL":
        return TrendState.UP
    if ind.ema21 < ind.ema50 < ind.ema200 and ind.structure == "LH_LL":
        return TrendState.DOWN
    if ind.ema9 > ind.ema21 > ind.ema50:
        return TrendState.UP
    if ind.ema9 < ind.ema21 < ind.ema50:
        return TrendState.DOWN
    return TrendState.SIDEWAYS


def select_modes(provider: MarketDataProvider, regime: MarketRegime) -> ModeDecision:
    """AI mode selector — prioritizes engines; may choose NO_TRADE. Does not place orders."""
    bars = provider.get_bars("XU100", 220)
    ind = compute_indicators(bars)
    atr_pct = (ind.atr14 / ind.ema21 * 100) if ind and ind.ema21 else 2.5
    vol = classify_volatility(atr_pct)
    trend = classify_trend(ind)
    cash = 0.15
    priorities: list[Horizon] = []

    if vol == VolatilityRegime.EXTREME or regime == MarketRegime.STRONG_BEAR:
        return ModeDecision(
            regime, vol, trend, [Horizon.NO_TRADE, Horizon.LONG_TERM], Horizon.NO_TRADE,
            "extreme_vol_or_strong_bear_capital_protection", cash_bias=0.55,
        )

    if regime == MarketRegime.STRONG_BULL and trend == TrendState.UP:
        priorities = [Horizon.LONG_TERM, Horizon.SWING, Horizon.DAY_TRADING]
        cash = 0.10
        reason = "strong_bull_trend_long_swing_focus"
    elif regime == MarketRegime.BULL and trend == TrendState.UP:
        priorities = [Horizon.SWING, Horizon.LONG_TERM, Horizon.DAY_TRADING]
        cash = 0.12
        reason = "bull_swing_primary"
    elif regime == MarketRegime.NEUTRAL or trend == TrendState.SIDEWAYS:
        priorities = [Horizon.SWING, Horizon.DAY_TRADING, Horizon.LONG_TERM]
        cash = 0.25
        reason = "sideways_selective_swing_mr"
    elif regime == MarketRegime.BEAR:
        priorities = [Horizon.LONG_TERM, Horizon.NO_TRADE, Horizon.SWING]
        cash = 0.40
        reason = "bear_raise_cash_selective_long_only"
    else:
        priorities = [Horizon.SWING, Horizon.LONG_TERM]
        cash = 0.20
        reason = "default_selective"

    if vol == VolatilityRegime.HIGH:
        # Reduce day trading priority
        priorities = [h for h in priorities if h != Horizon.DAY_TRADING] + [Horizon.DAY_TRADING]
        cash = min(0.5, cash + 0.1)
        reason += "+high_vol_day_deprioritized"

    primary = priorities[0] if priorities else Horizon.NO_TRADE
    return ModeDecision(regime, vol, trend, priorities, primary, reason, cash_bias=cash)
