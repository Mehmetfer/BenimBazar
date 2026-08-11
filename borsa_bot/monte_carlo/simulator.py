from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class MonteCarloReport:
    n_sims: int
    median_return: float
    p05_return: float
    p95_return: float
    median_max_dd: float
    p95_max_dd: float
    prob_ruin: float
    expected_max_losing_streak: float
    note: str


def _max_dd(equity: list[float]) -> float:
    peak = equity[0]
    mdd = 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak * 100 if peak else 0)
    return mdd


def run_monte_carlo(trade_pnls: list[float], *, n_sims: int = 500, start_equity: float = 100_000.0, ruin_pct: float = 40.0, seed: int = 42) -> MonteCarloReport:
    """Resample historical trade PnLs to estimate path risk. Not a guarantee."""
    if not trade_pnls:
        return MonteCarloReport(0, 0, 0, 0, 0, 0, 1.0, 0, "no_trades")
    rng = random.Random(seed)
    finals = []
    mdds = []
    ruins = 0
    streaks = []
    for _ in range(n_sims):
        eq = start_equity
        path = [eq]
        streak = max_streak = 0
        sample = [rng.choice(trade_pnls) for _ in trade_pnls]
        for pnl in sample:
            eq += pnl
            path.append(eq)
            if pnl < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        ret = (eq / start_equity - 1) * 100
        finals.append(ret)
        mdds.append(_max_dd(path))
        streaks.append(max_streak)
        if (start_equity - min(path)) / start_equity * 100 >= ruin_pct:
            ruins += 1
    finals.sort()
    mdds.sort()
    def pct(arr, p):
        return arr[int((len(arr) - 1) * p)]
    return MonteCarloReport(
        n_sims=n_sims,
        median_return=round(pct(finals, 0.5), 2),
        p05_return=round(pct(finals, 0.05), 2),
        p95_return=round(pct(finals, 0.95), 2),
        median_max_dd=round(pct(mdds, 0.5), 2),
        p95_max_dd=round(pct(mdds, 0.95), 2),
        prob_ruin=round(ruins / n_sims, 3),
        expected_max_losing_streak=round(sum(streaks) / len(streaks), 2),
        note="Simulated resampling — past paths ≠ future. Paper trading still required.",
    )
