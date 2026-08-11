from __future__ import annotations

from dataclasses import dataclass, field

from config.models import IndicatorSet, MarketRegime, SignalAction
from config.settings import settings
from factors.engine import FactorScores
from fundamental.provider import get_fundamentals
from profit.ev import estimate_p_win
from signals.engine import build_trade_plan


@dataclass
class HorizonOpportunity:
    horizon: str
    symbol: str
    decision: SignalAction
    score: float
    confidence: float
    win_probability: float
    expected_value: float
    risk_reward: float | None
    entry: float | None
    stop: float | None
    target1: float | None
    target2: float | None
    target3: float | None
    why_buy: list[str] = field(default_factory=list)
    why_now: list[str] = field(default_factory=list)
    what_can_go_wrong: list[str] = field(default_factory=list)
    sleeve: str = "LONG_TERM"
    category: str = "CORE"  # CORE/GROWTH/VALUE/MOMENTUM/DEFENSIVE/OPPORTUNISTIC


def long_term_score(factors: FactorScores, sector_score: float, regime: MarketRegime) -> float:
    f = factors
    # Quality + growth + value + financial stability (vol as stability proxy) + sector
    raw = (
        f.quality * 0.30
        + f.growth * 0.22
        + f.value * 0.18
        + f.momentum * 0.12  # long RS, not day noise
        + f.volatility * 0.10
        + sector_score * 0.08
    )
    if regime in {MarketRegime.BEAR, MarketRegime.STRONG_BEAR}:
        raw = raw * 0.85 + f.quality * 0.1  # quality tilt in stress
    # Value trap filter already in factor model; reinforce
    if f.value >= 65 and f.quality < 45:
        raw *= 0.7
    return round(max(0, min(100, raw)), 1)


def categorize(factors: FactorScores) -> str:
    if factors.quality >= 70 and factors.volatility >= 60:
        return "CORE"
    if factors.growth >= 65:
        return "GROWTH"
    if factors.value >= 65 and factors.quality >= 50:
        return "VALUE"
    if factors.momentum >= 70:
        return "MOMENTUM"
    if factors.volatility >= 70:
        return "DEFENSIVE"
    return "OPPORTUNISTIC"


def evaluate_long_term(
    *,
    symbol: str,
    price: float,
    ind: IndicatorSet,
    factors: FactorScores,
    sector_score: float,
    regime: MarketRegime,
    scores_final: float,
    conflict: bool,
) -> HorizonOpportunity:
    score = long_term_score(factors, sector_score, regime)
    fund = get_fundamentals(symbol)
    why, now, wrong = [], [], []
    if factors.quality >= 60:
        why.append("Quality factor constructive")
    if factors.growth >= 55:
        why.append("Growth profile supportive")
    if factors.value >= 55 and factors.quality >= 50:
        why.append("Value with quality floor")
    if sector_score >= 55:
        now.append("Sector relative strength supportive")
    if regime in {MarketRegime.BULL, MarketRegime.STRONG_BULL}:
        now.append("Market regime supports compounding")
    if fund.available and (fund.debt_equity or 0) > 1.5:
        wrong.append("Elevated leverage")
    if factors.value >= 70 and factors.quality < 50:
        wrong.append("Possible value trap")
    wrong.append("Thesis can break on earnings/sector regime shift")

    plan = build_trade_plan(price, ind)
    # Wider conceptual horizon — still use structure stop for risk framing
    rr = plan.risk_reward if plan else None
    from config.models import ScoreBundle
    dummy = ScoreBundle(score, factors.quality, 70, sector_score, factors.momentum, 50, 50, 70, 30, 70, score)
    p_win = estimate_p_win(dummy, regime=regime, conflict=conflict, mtf_aligned=True)
    ev = p_win * (rr or 1.5) * 2 - (1 - p_win) * 2  # illustrative R multiples

    if conflict or score < settings.watch_threshold:
        decision = SignalAction.WATCH if score >= 55 else SignalAction.NO_TRADE
    elif score >= settings.strong_buy_threshold and factors.quality >= 55 and ev > 0:
        decision = SignalAction.STRONG_BUY
    elif score >= settings.buy_score_threshold and ev > 0 and factors.quality >= 50:
        decision = SignalAction.BUY
    elif score >= settings.watch_threshold:
        decision = SignalAction.WATCH
    else:
        decision = SignalAction.NO_TRADE

    return HorizonOpportunity(
        horizon="LONG_TERM",
        symbol=symbol,
        decision=decision,
        score=score,
        confidence=round(min(95, score * 0.7 + factors.quality * 0.3), 1),
        win_probability=round(p_win, 3),
        expected_value=round(ev, 3),
        risk_reward=rr,
        entry=plan.entry if plan else price,
        stop=plan.stop if plan else None,
        target1=plan.target1 if plan else None,
        target2=plan.target2 if plan else None,
        target3=plan.target3 if plan else None,
        why_buy=why,
        why_now=now,
        what_can_go_wrong=wrong,
        sleeve="LONG_TERM",
        category=categorize(factors),
    )
