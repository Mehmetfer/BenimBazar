from __future__ import annotations

from dataclasses import dataclass

from config.models import MarketRegime


# Regime-aware strategy weights (sum need not be 1; used as relative importance)
REGIME_STRATEGY_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.STRONG_BULL: {
        "trend_following": 1.4,
        "breakout": 1.3,
        "volume_breakout": 1.2,
        "momentum": 1.0,
        "ema_crossover": 0.9,
        "mean_reversion": 0.3,
        "pullback": 0.7,
    },
    MarketRegime.BULL: {
        "trend_following": 1.2,
        "momentum": 1.2,
        "pullback": 1.1,
        "ema_crossover": 1.0,
        "breakout": 0.9,
        "volume_breakout": 0.9,
        "mean_reversion": 0.5,
    },
    MarketRegime.NEUTRAL: {
        "mean_reversion": 1.3,
        "breakout": 1.1,
        "volume_breakout": 0.9,
        "pullback": 0.8,
        "momentum": 0.6,
        "trend_following": 0.5,
        "ema_crossover": 0.6,
    },
    MarketRegime.BEAR: {
        "mean_reversion": 0.6,
        "trend_following": 0.3,
        "breakout": 0.3,
        "momentum": 0.3,
        "pullback": 0.4,
        "ema_crossover": 0.3,
        "volume_breakout": 0.3,
    },
    MarketRegime.STRONG_BEAR: {
        "trend_following": 0.1,
        "breakout": 0.1,
        "momentum": 0.1,
        "mean_reversion": 0.2,
        "pullback": 0.1,
        "ema_crossover": 0.1,
        "volume_breakout": 0.1,
    },
}


def vote_pullback(ind, close: float) -> str:
    """Pullback in uptrend: price near EMA21 with RSI reset."""
    if ind.ema9 > ind.ema21 > ind.ema50 and close <= ind.ema21 * 1.01 and 40 <= ind.rsi14 <= 55:
        return "AL"
    if ind.ema9 < ind.ema21 < ind.ema50 and close >= ind.ema21 * 0.99 and 45 <= ind.rsi14 <= 60:
        return "SAT"
    return "BEKLE"


@dataclass
class StrategyPerf:
    name: str
    net_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    calmar: float
    profit_factor: float
    expectancy: float

    @property
    def risk_adjusted_score(self) -> float:
        """Higher is better. Punish large drawdowns heavily."""
        dd_pen = max(self.max_drawdown, 0.1)
        # Prefer calmar/sharpe; penalize DD > 20 hard
        score = (
            self.net_return * 0.25
            + self.sharpe * 15
            + self.sortino * 10
            + self.calmar * 12
            + self.profit_factor * 8
            + self.expectancy * 0.05
            - dd_pen * 1.8
        )
        if self.max_drawdown >= 45:
            score -= 40
        elif self.max_drawdown >= 25:
            score -= 20
        elif self.max_drawdown >= 15:
            score -= 8
        return round(score, 2)


def rank_strategies(perfs: list[StrategyPerf]) -> list[StrategyPerf]:
    """Do NOT auto-select highest return — report risk-adjusted ranking."""
    return sorted(perfs, key=lambda p: p.risk_adjusted_score, reverse=True)


def example_ranking_report() -> list[dict]:
    """DEAD / ILLUSTRATIVE ONLY — static samples for docs/tests.

    Production paper feedback uses analytics.paper_feedback.PaperDecisionFeedback.ranking_report().
    Do not treat this as live strategy championship or auto-switch.
    """
    samples = [
        StrategyPerf("A_aggressive", 80, 45, 0.8, 1.0, 1.8, 1.4, 120),
        StrategyPerf("B_balanced", 45, 12, 1.4, 1.8, 3.7, 1.7, 90),
        StrategyPerf("C_conservative", 38, 8, 1.6, 2.1, 4.7, 1.9, 70),
    ]
    ranked = rank_strategies(samples)
    return [
        {
            "rank": i + 1,
            "name": s.name,
            "return": s.net_return,
            "max_dd": s.max_drawdown,
            "risk_adjusted_score": s.risk_adjusted_score,
            "dead_illustrative": True,
        }
        for i, s in enumerate(ranked)
    ]
