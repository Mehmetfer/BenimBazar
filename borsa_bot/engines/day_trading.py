from __future__ import annotations

from config.models import IndicatorSet, MarketRegime, QuoteSnapshot, ScoreBundle, SignalAction
from config.settings import settings
from engines.long_term import HorizonOpportunity
from engines.mode_selector import VolatilityRegime
from profit.ev import estimate_p_win
from signals.engine import build_trade_plan
from technical.price_action import PriceActionView


def opening_range_break(bars, lookback: int = 8) -> tuple[bool, bool]:
    """Proxy ORB using first N bars of available history window end — simulator approximation."""
    if len(bars) < lookback + 2:
        return False, False
    window = bars[-(lookback + 5) : -2]
    if len(window) < lookback:
        return False, False
    hi = max(b.high for b in window[:lookback])
    lo = min(b.low for b in window[:lookback])
    last = bars[-1].close
    return last > hi, last < lo


def evaluate_day(
    *,
    symbol: str,
    quote: QuoteSnapshot,
    ind: IndicatorSet,
    regime: MarketRegime,
    vol_regime: VolatilityRegime,
    pa: PriceActionView,
    mtf: dict[str, str],
    index_bullish: bool,
    conflict: bool,
    day_paused: bool,
) -> HorizonOpportunity:
    price = quote.price
    why, now, wrong = [], [], []

    # Hard filters
    if day_paused:
        return _no(symbol, price, "day_trading_paused", ind)
    if quote.spread_pct > settings.max_spread_pct * 0.75:
        return _no(symbol, price, "spread_too_wide_for_day", ind)
    if vol_regime == VolatilityRegime.EXTREME:
        return _no(symbol, price, "extreme_volatility", ind)
    if not index_bullish and regime in {MarketRegime.BEAR, MarketRegime.STRONG_BEAR}:
        return _no(symbol, price, "market_direction_hostile", ind)
    if conflict:
        return _no(symbol, price, "signal_conflict", ind)

    rvol = quote.volume / ind.vol_sma20 if ind.vol_sma20 else 1.0
    above_vwap = price > ind.vwap
    # Simulator lacks true session opening range — require volume-confirmed breakout above VWAP instead (honest).
    orb_up = pa.breakout and pa.volume_confirmed and above_vwap

    score = 40.0
    if above_vwap:
        score += 12
        why.append("Price above VWAP")
    if rvol >= 1.4:
        score += 15
        now.append("Relative volume elevated")
    elif rvol < 0.7:
        score -= 15
        wrong.append("Weak relative volume")
    if pa.pattern == "BREAKOUT" and pa.volume_confirmed:
        score += 18
        now.append("Volume-confirmed breakout")
    if pa.false_breakout:
        score -= 25
        wrong.append("False breakout risk")
    if mtf.get("15m") == "BULL" and mtf.get("1h") == "BEAR":
        score -= 20
        wrong.append("15m vs 1h conflict")
    if index_bullish:
        score += 8
    score = round(max(0, min(100, score)), 1)

    plan = build_trade_plan(price, ind)
    # Day stops typically tighter — use 1.2x ATR conceptually if plan exists
    if plan:
        tight_stop = price - ind.atr14 * 1.2
        if tight_stop < price:
            plan.stop = round(max(tight_stop, plan.stop), 2) if plan.stop < price else round(tight_stop, 2)
            risk = price - plan.stop
            if risk > 0:
                plan.target1 = round(price + risk * 1.5, 2)
                plan.target2 = round(price + risk * 2.0, 2)
                plan.target3 = round(price + risk * 2.5, 2)
                plan.risk_reward = round((plan.target1 - price) / risk, 2)

    rr = plan.risk_reward if plan else None
    dummy = ScoreBundle(score, 50, 55, 50, 60, min(100, rvol * 40), 50, 80 if quote.spread_pct < 0.3 else 40, 40, 65, score)
    p_win = estimate_p_win(dummy, regime=regime, conflict=False, mtf_aligned=mtf.get("1h") == "BULL")
    risk_pct = ((plan.entry - plan.stop) / plan.entry * 100) if plan else 2
    reward_pct = ((plan.target1 - plan.entry) / plan.entry * 100) if plan else 3
    ev = p_win * reward_pct - (1 - p_win) * risk_pct

    if not orb_up or ev <= 0 or (rr is not None and rr < settings.min_risk_reward):
        decision = SignalAction.WATCH if score >= 60 else SignalAction.NO_TRADE
    elif score >= 85 and rvol >= 1.5 and above_vwap:
        decision = SignalAction.STRONG_BUY
    elif score >= 78 and above_vwap:
        decision = SignalAction.BUY
    elif score >= 60:
        decision = SignalAction.WATCH
    else:
        decision = SignalAction.NO_TRADE

    wrong.append("Day setups expire — no overnight hold by default")
    return HorizonOpportunity(
        horizon="DAY_TRADING",
        symbol=symbol,
        decision=decision,
        score=score,
        confidence=round(min(92, score * 0.7 + min(20, rvol * 8)), 1),
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
        sleeve="DAY_TRADING",
        category="OPPORTUNISTIC",
    )


def _no(symbol: str, price: float, reason: str, ind: IndicatorSet) -> HorizonOpportunity:
    return HorizonOpportunity(
        horizon="DAY_TRADING",
        symbol=symbol,
        decision=SignalAction.NO_TRADE,
        score=0,
        confidence=10,
        win_probability=0.0,
        expected_value=-1.0,
        risk_reward=None,
        entry=price,
        stop=None,
        target1=None,
        target2=None,
        target3=None,
        why_buy=[],
        why_now=[],
        what_can_go_wrong=[reason],
        sleeve="DAY_TRADING",
    )
