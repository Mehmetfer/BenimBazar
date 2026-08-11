from __future__ import annotations

from dataclasses import dataclass

from config.models import FundamentalSnapshot, IndicatorSet
from fundamental.provider import get_fundamentals


@dataclass
class FactorScores:
    momentum: float
    value: float
    quality: float
    growth: float
    volatility: float  # higher = calmer / more investable (inverted raw vol)

    def as_dict(self) -> dict[str, float]:
        return {
            "momentum": self.momentum,
            "value": self.value,
            "quality": self.quality,
            "growth": self.growth,
            "volatility": self.volatility,
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _ret(closes: list[float], n: int) -> float:
    if len(closes) <= n or closes[-n - 1] == 0:
        return 0.0
    return closes[-1] / closes[-n - 1] - 1


def momentum_factor(closes: list[float], rs_vs_index: float = 0.0) -> float:
    """1M/3M/6M/12M + 12-1 style when history allows; simulated bars ≈ 15m so use bar counts as proxy."""
    # Proxy horizons in bars for MVP simulator (not calendar months)
    r_1 = _ret(closes, 20)
    r_3 = _ret(closes, 60)
    r_6 = _ret(closes, 120)
    r_12 = _ret(closes, 200) if len(closes) > 200 else _ret(closes, 160)
    # 12-1: long horizon minus recent month
    r_12_1 = r_12 - r_1
    # consistency: how many horizons positive
    signs = sum(1 for r in (r_1, r_3, r_6, r_12) if r > 0)
    accel = r_1 - r_3
    raw = (
        50
        + r_1 * 80
        + r_3 * 60
        + r_6 * 40
        + r_12_1 * 50
        + rs_vs_index * 40
        + (signs - 2) * 5
        + accel * 30
    )
    return round(_clamp(raw), 1)


def value_factor(f: FundamentalSnapshot) -> float:
    if not f.available:
        return 50.0  # neutral — do not invent cheapness
    score = 50.0
    pe = f.pe or 15
    pb = f.pb or 1.5
    if 4 <= pe <= 12:
        score += 15
    elif pe > 25:
        score -= 12
    if pb <= 1.2:
        score += 10
    elif pb > 4:
        score -= 8
    return round(_clamp(score), 1)


def quality_factor(f: FundamentalSnapshot) -> float:
    if not f.available:
        return 50.0
    score = 50.0
    if (f.roe or 0) >= 0.15:
        score += 12
    if (f.roa or 0) >= 0.06:
        score += 8
    if (f.net_margin or 0) >= 0.08:
        score += 8
    if (f.op_margin or 0) >= 0.1:
        score += 6
    if (f.debt_equity or 0) > 1.5:
        score -= 15
    if (f.current_ratio or 1) < 1:
        score -= 8
    if (f.ocf or 0) > 0 or (f.fcf or 0) > 0:
        score += 5
    return round(_clamp(score), 1)


def growth_factor(f: FundamentalSnapshot) -> float:
    if not f.available:
        return 50.0
    score = 50.0
    score += min(20, max(-15, (f.revenue_growth or 0) * 80))
    score += min(20, max(-15, (f.earnings_growth or 0) * 70))
    score += min(10, max(-10, (f.equity_growth or 0) * 50))
    return round(_clamp(score), 1)


def volatility_factor(ind: IndicatorSet, price: float) -> float:
    """Higher score = more tradable / less chaotic."""
    atr_pct = ind.atr14 / price * 100 if price else 5
    # downside proxy via structure
    pen = 10 if ind.structure == "LH_LL" else 0
    raw = 100 - atr_pct * 12 - pen
    return round(_clamp(raw), 1)


def compute_factors(
    symbol: str,
    closes: list[float],
    ind: IndicatorSet,
    price: float,
    rs_vs_index: float = 0.0,
) -> FactorScores:
    f = get_fundamentals(symbol)
    return FactorScores(
        momentum=momentum_factor(closes, rs_vs_index),
        value=value_factor(f),
        quality=quality_factor(f),
        growth=growth_factor(f),
        volatility=volatility_factor(ind, price),
    )
