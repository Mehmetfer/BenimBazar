from __future__ import annotations

from config.models import IndicatorSet, MarketRegime, SignalAction
from config.settings import settings
from engines.long_term import HorizonOpportunity
from factors.engine import FactorScores
from profit.ev import estimate_p_win
from signals.engine import build_trade_plan
from technical.price_action import PriceActionView
from config.models import ScoreBundle


def evaluate_swing(
    *,
    symbol: str,
    price: float,
    ind: IndicatorSet,
    factors: FactorScores,
    sector_score: float,
    regime: MarketRegime,
    mtf: dict[str, str],
    pa: PriceActionView,
    conflict: bool,
    volume_score: float,
) -> HorizonOpportunity:
    # Multi-timeframe confirmation
    higher = [mtf.get(k) for k in ("1w", "1d", "4h") if mtf.get(k) not in (None, "UNAVAILABLE", "INSUFFICIENT")]
    lower = [mtf.get(k) for k in ("1h", "30m", "15m") if mtf.get(k) not in (None, "UNAVAILABLE", "INSUFFICIENT")]
    h_bull = sum(1 for x in higher if x == "BULL")
    l_bull = sum(1 for x in lower if x == "BULL")
    aligned = h_bull >= 2 and l_bull >= 1

    score = (
        (25 if ind.ema9 > ind.ema21 > ind.ema50 else 8)
        + min(20, max(0, ind.adx14))
        + (15 if factors.momentum >= 55 else 5)
        + (12 if volume_score >= 60 else 4)
        + (12 if aligned else 0)
        + (10 if pa.pattern in {"BREAKOUT", "SUPPORT_BOUNCE", "TREND_CONTINUATION"} and pa.volume_confirmed else 0)
        + (8 if sector_score >= 55 else 2)
    )
    if pa.false_breakout or (pa.breakout and not pa.volume_confirmed):
        score *= 0.55
    if regime == MarketRegime.STRONG_BEAR:
        score *= 0.4
    elif regime == MarketRegime.BEAR:
        score *= 0.65
    score = round(max(0, min(100, score)), 1)

    plan = build_trade_plan(price, ind)
    rr = plan.risk_reward if plan else None
    dummy = ScoreBundle(score, 50, 60, sector_score, factors.momentum, volume_score, 50, 70, 35, 70, score)
    p_win = estimate_p_win(dummy, regime=regime, conflict=conflict or not aligned, mtf_aligned=aligned)
    risk_pct = ((plan.entry - plan.stop) / plan.entry * 100) if plan else 3
    reward_pct = ((plan.target1 - plan.entry) / plan.entry * 100) if plan else 4.5
    ev = p_win * reward_pct - (1 - p_win) * risk_pct

    why = []
    now = []
    wrong = []
    if aligned:
        why.append("Higher TF trend aligned")
    if ind.ema9 > ind.ema21 > ind.ema50:
        why.append("EMA stack bullish")
    if pa.volume_confirmed:
        now.append("Volume-confirmed price action")
    if factors.momentum >= 60:
        now.append("Momentum factor supportive")
    if not aligned and l_bull and h_bull == 0:
        wrong.append("Lower TF bounce vs higher TF bear — false breakout risk")
    if conflict:
        wrong.append("Signal conflict")
    wrong.append("Swing thesis fails if daily structure breaks")

    if ev <= settings.min_expected_value or conflict or (pa.breakout and not pa.volume_confirmed):
        decision = SignalAction.NO_TRADE if score < 55 else SignalAction.WAIT
    elif score >= settings.strong_buy_threshold and aligned and rr and rr >= 2:
        decision = SignalAction.STRONG_BUY
    elif score >= settings.buy_score_threshold and rr and rr >= settings.min_risk_reward:
        decision = SignalAction.BUY
    elif score >= settings.watch_threshold:
        decision = SignalAction.WATCH
    else:
        decision = SignalAction.NO_TRADE

    return HorizonOpportunity(
        horizon="SWING",
        symbol=symbol,
        decision=decision,
        score=score,
        confidence=round(min(95, score * 0.65 + (15 if aligned else 0) + volume_score * 0.15), 1),
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
        sleeve="SWING",
        category="MOMENTUM" if factors.momentum >= 60 else "OPPORTUNISTIC",
    )
