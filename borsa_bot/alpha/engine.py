from __future__ import annotations

from dataclasses import dataclass, field

from config.models import IndicatorSet, MarketRegime
from factors.engine import FactorScores
from strategy.modules import (
    vote_breakout,
    vote_ema_crossover,
    vote_mean_reversion,
    vote_momentum,
    vote_trend_following,
    vote_volume_breakout,
)
from strategy.ranking import vote_pullback


@dataclass
class AlphaSignal:
    name: str
    signal: str  # AL / SAT / BEKLE
    confidence: float
    historical_expectancy: float  # illustrative placeholder until calibrated
    win_rate: float
    max_dd: float
    regime_fit: float
    notes: list[str] = field(default_factory=list)


# Illustrative historical stats by strategy (NOT live performance claims)
_HIST = {
    "trend_following": (12.0, 0.52, 18.0),
    "momentum": (10.0, 0.50, 20.0),
    "breakout": (9.0, 0.48, 22.0),
    "pullback": (8.0, 0.54, 14.0),
    "mean_reversion": (6.0, 0.55, 12.0),
    "volume_breakout": (8.5, 0.49, 21.0),
    "relative_strength": (11.0, 0.51, 16.0),
    "factor_model": (9.5, 0.53, 15.0),
}


def _regime_fit(name: str, regime: MarketRegime) -> float:
    table = {
        MarketRegime.STRONG_BULL: {
            "trend_following": 1.0, "momentum": 0.95, "breakout": 0.9, "pullback": 0.7,
            "mean_reversion": 0.3, "volume_breakout": 0.85, "relative_strength": 0.95, "factor_model": 0.8,
        },
        MarketRegime.BULL: {
            "trend_following": 0.9, "momentum": 0.9, "breakout": 0.75, "pullback": 0.9,
            "mean_reversion": 0.45, "volume_breakout": 0.75, "relative_strength": 0.9, "factor_model": 0.85,
        },
        MarketRegime.NEUTRAL: {
            "trend_following": 0.4, "momentum": 0.5, "breakout": 0.7, "pullback": 0.6,
            "mean_reversion": 0.95, "volume_breakout": 0.65, "relative_strength": 0.55, "factor_model": 0.7,
        },
        MarketRegime.BEAR: {
            "trend_following": 0.25, "momentum": 0.3, "breakout": 0.25, "pullback": 0.35,
            "mean_reversion": 0.5, "volume_breakout": 0.25, "relative_strength": 0.35, "factor_model": 0.45,
        },
        MarketRegime.STRONG_BEAR: {
            "trend_following": 0.1, "momentum": 0.1, "breakout": 0.1, "pullback": 0.1,
            "mean_reversion": 0.2, "volume_breakout": 0.1, "relative_strength": 0.15, "factor_model": 0.25,
        },
    }
    return table.get(regime, table[MarketRegime.NEUTRAL]).get(name, 0.5)


def _rs_vote(factors: FactorScores) -> str:
    if factors.momentum >= 65 and factors.quality >= 50:
        return "AL"
    if factors.momentum <= 35:
        return "SAT"
    return "BEKLE"


def _factor_vote(factors: FactorScores) -> str:
    # Cheap+junk rejected: require quality floor with value
    composite = factors.momentum * 0.3 + factors.quality * 0.25 + factors.growth * 0.2 + factors.value * 0.15 + factors.volatility * 0.1
    if factors.value >= 60 and factors.quality < 45:
        return "BEKLE"  # value trap filter
    if composite >= 62:
        return "AL"
    if composite <= 38:
        return "SAT"
    return "BEKLE"


def run_alpha_ensemble(
    ind: IndicatorSet,
    close: float,
    volume: float,
    factors: FactorScores,
    regime: MarketRegime,
) -> list[AlphaSignal]:
    raw_votes = {
        "trend_following": vote_trend_following(ind),
        "momentum": vote_momentum(ind),
        "breakout": vote_breakout(ind, close),
        "pullback": vote_pullback(ind, close),
        "mean_reversion": vote_mean_reversion(ind),
        "volume_breakout": vote_volume_breakout(ind, volume, close),
        "relative_strength": _rs_vote(factors),
        "factor_model": _factor_vote(factors),
        "ema_crossover": vote_ema_crossover(ind),
    }
    out: list[AlphaSignal] = []
    for name, sig in raw_votes.items():
        if name == "ema_crossover":
            # correlated with trend — keep but lower confidence (not independent evidence)
            exp, wr, dd = 7.0, 0.5, 17.0
        else:
            exp, wr, dd = _HIST.get(name, (5.0, 0.5, 20.0))
        fit = _regime_fit(name if name != "ema_crossover" else "trend_following", regime)
        conf = 55.0
        if sig == "AL":
            conf += 15 * fit
        elif sig == "SAT":
            conf += 10 * fit
        else:
            conf -= 5
        if name == "ema_crossover":
            conf *= 0.7
            notes = ["correlated_with_trend_not_independent"]
        else:
            notes = [f"regime_fit={fit:.2f}"]
        if regime == MarketRegime.STRONG_BEAR and sig == "AL":
            conf *= 0.4
            notes.append("strong_bear_long_penalty")
        out.append(
            AlphaSignal(
                name=name,
                signal=sig,
                confidence=round(min(95, conf), 1),
                historical_expectancy=exp,
                win_rate=wr,
                max_dd=dd,
                regime_fit=fit,
                notes=notes,
            )
        )
    return out


def aggregate_alpha(alphas: list[AlphaSignal]) -> tuple[float, str, list[str]]:
    """Weighted buy bias; does not authorize trades."""
    score = 0.0
    wsum = 0.0
    notes = []
    for a in alphas:
        w = a.regime_fit * (a.confidence / 100) * max(0.2, 1 - a.max_dd / 100)
        wsum += w
        if a.signal == "AL":
            score += w
        elif a.signal == "SAT":
            score -= w
        if a.regime_fit < 0.35 and a.signal == "AL":
            notes.append(f"{a.name}_poor_regime")
    bias = score / wsum if wsum else 0
    label = "AL" if bias > 0.25 else ("SAT" if bias < -0.25 else "BEKLE")
    return round(bias, 3), label, notes
