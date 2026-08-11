from __future__ import annotations

from config.models import (
    IndicatorSet,
    MarketRegime,
    NewsItem,
    ScoreBundle,
    SignalAction,
    TradePlan,
)
from config.settings import settings
from fundamental.provider import score_fundamentals, get_fundamentals
from market_regime.engine import regime_buy_threshold_boost, trend_label
from news.analyzer import classify_headline, latest_stub_headline, score_news
from strategy.modules import ensemble_votes
from technical.mtf import analyze_mtf, mtf_conflict_risk


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def technical_score(ind: IndicatorSet, close: float) -> tuple[float, list[str]]:
    """Composite technical — never a single indicator alone."""
    reasons: list[str] = []
    # Trend cluster (correlated EMAs counted as ONE cluster, not independent votes)
    trend = 0.0
    if ind.ema9 > ind.ema21 > ind.ema50 > ind.ema100:
        trend = 22
        reasons.append("EMA trend bullish")
    elif ind.ema9 > ind.ema21 > ind.ema50:
        trend = 14
        reasons.append("EMA short/mid bullish")
    elif ind.ema9 < ind.ema21 < ind.ema50:
        trend = 2
        reasons.append("EMA bearish")
    else:
        trend = 8
    if close > ind.ema200:
        trend += 6
    else:
        trend -= 2

    # Momentum cluster (ROC/Momentum/RSI related — blended, not triple counted)
    mom = _clamp((ind.momentum10 + ind.roc12 / 2 + 4) / 8 * 18)
    if 40 <= ind.rsi14 <= 65:
        mom += 4
        reasons.append("RSI constructive")
    elif ind.rsi14 > 75:
        mom -= 6
        reasons.append("RSI overbought")

    # MACD as confirmation only
    macd_s = 12 if ind.macd_hist > 0 and ind.macd > ind.macd_signal else 4
    if macd_s >= 12:
        reasons.append("MACD positive")

    # Structure / BB / ADX
    struct = 10 if ind.structure == "HH_HL" else (3 if ind.structure == "LH_LL" else 6)
    adx_s = 10 if ind.adx14 >= 20 else 4
    if ind.adx14 >= 20:
        reasons.append("ADX trend strength ok")

    # Volume / money flow cluster (OBV/MFI/CMF related)
    flow = 5
    if ind.cmf20 > 0.05 and ind.mfi14 >= 45:
        flow = 12
        reasons.append("money flow supportive")
    elif ind.cmf20 < -0.05:
        flow = 2

    total = trend + mom * 0.7 + macd_s + struct + adx_s + flow
    # Stoch / StochRSI as soft confirmation only (not independent thesis)
    if ind.stoch_k > ind.stoch_d and ind.stoch_k < 80:
        total += 3
    if close > ind.vwap:
        total += 3
    return round(_clamp(total), 1), reasons


def momentum_score(ind: IndicatorSet) -> float:
    return round(_clamp(50 + ind.momentum10 * 8 + ind.roc12 * 2), 1)


def volume_score(ind: IndicatorSet, volume: float) -> tuple[float, list[str]]:
    notes = []
    ratio = volume / ind.vol_sma20 if ind.vol_sma20 else 1.0
    score = _clamp((ratio - 0.6) / 1.2 * 100)
    if ratio >= 1.4:
        notes.append("Volume confirms breakout")
    elif ratio < 0.7:
        notes.append("Volume weak")
    return round(score, 1), notes


def market_score(regime: MarketRegime, index_bullish: bool) -> float:
    base = {
        MarketRegime.STRONG_BULL: 90,
        MarketRegime.BULL: 75,
        MarketRegime.NEUTRAL: 50,
        MarketRegime.BEAR: 30,
        MarketRegime.STRONG_BEAR: 15,
    }[regime]
    if index_bullish:
        base = min(100, base + 5)
    return float(base)


def risk_score_components(
    *,
    atr_pct: float,
    spread_pct: float,
    conflict: bool,
    news_block: bool,
    rr: float | None,
    liquidity: float,
) -> tuple[float, list[str]]:
    """Higher = safer (inverted later for RISK_SCORE display as riskiness)."""
    notes = []
    safety = 80.0
    if atr_pct > 4:
        safety -= 20
        notes.append("ATR elevated")
    if spread_pct > 0.4:
        safety -= 15
        notes.append("spread elevated")
    if conflict:
        safety -= 25
        notes.append("signal conflict")
    if news_block:
        safety -= 30
        notes.append("news risk")
    if rr is not None and rr < settings.min_risk_reward:
        safety -= 25
        notes.append("RR insufficient")
    if liquidity < 50:
        safety -= 15
        notes.append("liquidity risk")
    return round(_clamp(safety), 1), notes


def detect_conflict(scores: ScoreBundle, risk_level_high: bool) -> tuple[bool, str]:
    if scores.technical >= 85 and scores.market <= 45:
        return True, "strong_technical_weak_market"
    if scores.technical >= 85 and scores.fundamental >= 80 and risk_level_high:
        return True, "scores_ok_but_risk_high"
    if scores.sector < 40 and scores.technical >= 80:
        return True, "weak_sector_vs_technical"
    if abs(scores.technical - scores.momentum) > 45:
        return True, "technical_momentum_divergence"
    return False, ""


def build_trade_plan(price: float, ind: IndicatorSet) -> TradePlan | None:
    atr_stop = price - ind.atr14 * settings.atr_stop_mult
    # Prefer stop slightly beyond nearby support to reduce stop-hunt, without inventing false precision
    structural = ind.support * 0.998 if ind.support < price else atr_stop
    stop = min(atr_stop, structural)
    if stop <= 0 or stop >= price:
        return None
    risk = price - stop
    t1 = price + risk * settings.min_risk_reward
    t2 = price + risk * settings.preferred_risk_reward
    t3 = price + risk * max(settings.preferred_risk_reward, settings.atr_take_mult)
    # Cap targets near resistance awareness
    if ind.resistance > price:
        t1 = min(t1, ind.resistance)
    rr = (t1 - price) / risk if risk else 0
    if rr < settings.min_risk_reward:
        # try ATR-only targets
        t1 = price + risk * settings.min_risk_reward
        t2 = price + risk * settings.preferred_risk_reward
        t3 = price + risk * 3.0
        rr = (t1 - price) / risk
    if rr < settings.min_risk_reward:
        return None
    return TradePlan(
        entry=round(price, 2),
        stop=round(stop, 2),
        target1=round(t1, 2),
        target2=round(t2, 2),
        target3=round(t3, 2),
        risk_reward=round(rr, 2),
    )


def compose_scores(
    *,
    ind: IndicatorSet,
    close: float,
    volume: float,
    regime: MarketRegime,
    index_bullish: bool,
    sector_sc: float,
    liquidity: float,
    news_item: NewsItem | None,
    ai_confidence: float,
    spread_pct: float,
    mtf_conflict: bool,
) -> tuple[ScoreBundle, list[str], list[str], TradePlan | None, bool]:
    tech, tech_reasons = technical_score(ind, close)
    fund, fund_notes = score_fundamentals(get_fundamentals(""))  # placeholder overridden by caller
    # fund filled by caller usually — keep neutral if empty symbol used
    mom = momentum_score(ind)
    vol, vol_notes = volume_score(ind, volume)
    mkt = market_score(regime, index_bullish)
    news_sc, news_notes, news_block = score_news(
        news_item or classify_headline("X", None)
    )
    plan = build_trade_plan(close, ind)
    rr = plan.risk_reward if plan else None
    safety, risk_notes = risk_score_components(
        atr_pct=ind.atr14 / close * 100 if close else 5,
        spread_pct=spread_pct,
        conflict=mtf_conflict,
        news_block=news_block,
        rr=rr,
        liquidity=liquidity,
    )
    # Final weighted score — risk/market can veto later
    final = (
        tech * 0.25
        + fund * 0.10
        + mkt * 0.15
        + sector_sc * 0.12
        + mom * 0.10
        + vol * 0.10
        + news_sc * 0.05
        + liquidity * 0.08
        + safety * 0.05
    )
    # Soft AI influence (never decisive alone)
    final = final * 0.9 + ai_confidence * 0.1
    if regime == MarketRegime.STRONG_BEAR:
        final *= 0.75
    elif regime == MarketRegime.BEAR:
        final *= 0.85
    bundle = ScoreBundle(
        technical=round(tech, 1),
        fundamental=round(fund, 1),
        market=round(mkt, 1),
        sector=round(sector_sc, 1),
        momentum=round(mom, 1),
        volume=round(vol, 1),
        news=round(news_sc, 1),
        liquidity=round(liquidity, 1),
        risk=round(100 - safety, 1),  # riskiness
        ai_confidence=round(ai_confidence, 1),
        final=round(_clamp(final), 1),
    )
    reasons = tech_reasons + vol_notes + fund_notes + news_notes
    risks = risk_notes
    return bundle, reasons, risks, plan, news_block


def decide_from_scores(
    scores: ScoreBundle,
    *,
    owned: bool,
    regime: MarketRegime,
    conflict: bool,
    news_block: bool,
    plan: TradePlan | None,
    sell_pressure: float,
) -> SignalAction:
    if news_block or conflict or plan is None:
        return SignalAction.BEKLE
    boost = regime_buy_threshold_boost(regime)
    buy_th = settings.buy_score_threshold + boost
    if owned and sell_pressure >= settings.sell_score_threshold:
        return SignalAction.SAT
    if owned:
        return SignalAction.BEKLE
    if scores.final >= settings.strong_buy_threshold and scores.market >= 60 and scores.risk <= 40:
        return SignalAction.AL
    if scores.final >= buy_th and scores.market >= 50 and scores.risk <= 45:
        return SignalAction.AL
    if scores.final >= settings.watch_threshold:
        return SignalAction.BEKLE  # WATCH mapped to BEKLE for execution safety
    if scores.final < 40:
        return SignalAction.ALMA
    return SignalAction.BEKLE


def score_buy(ind: IndicatorSet, close: float, volume: float, regime: MarketRegime, index_bullish: bool) -> float:
    """Legacy helper for backtests."""
    tech, _ = technical_score(ind, close)
    vol, _ = volume_score(ind, volume)
    mkt = market_score(regime, index_bullish)
    return round(_clamp(tech * 0.5 + vol * 0.2 + mkt * 0.3), 1)


def score_sell(ind: IndicatorSet, close: float, volume: float, owned: bool) -> float:
    trend = 20 if ind.ema9 < ind.ema21 < ind.ema50 else 5
    mom = _clamp((-ind.momentum10 + 3) / 6 * 15)
    rsi_s = 15 if ind.rsi14 >= 70 else (8 if ind.rsi14 >= 60 else 3)
    macd_s = 15 if ind.macd_hist < 0 and ind.macd < ind.macd_signal else 4
    total = trend + mom + rsi_s + macd_s
    if not owned:
        total *= 0.55
    return round(_clamp(total), 1)


def decide_action(buy_score: float, sell_score: float, owned: bool, regime: MarketRegime) -> SignalAction:
    if owned and sell_score >= settings.sell_score_threshold:
        return SignalAction.SAT
    if (not owned) and buy_score >= settings.buy_score_threshold:
        if regime == MarketRegime.STRONG_BEAR:
            return SignalAction.BEKLE
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
