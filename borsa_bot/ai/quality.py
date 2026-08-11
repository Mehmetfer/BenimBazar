from __future__ import annotations

from config.models import IndicatorSet, MarketRegime, SignalAction


def assess_signal_quality(
    *,
    action: SignalAction,
    buy_score: float,
    sell_score: float,
    ind: IndicatorSet,
    regime: MarketRegime,
    spread_pct: float,
) -> tuple[float, str]:
    """AI layer: quality/confidence only — never issues final trade permission."""
    conf = 50.0
    notes = []
    score = buy_score if action in {SignalAction.AL, SignalAction.ALMA, SignalAction.BEKLE} else sell_score
    conf += min(25, abs(score - 50) * 0.5)
    if ind.adx14 >= 20:
        conf += 8
        notes.append("trend_strength_ok")
    else:
        conf -= 5
        notes.append("weak_adx")
    if spread_pct > 0.35:
        conf -= 15
        notes.append("wide_spread")
    if regime == MarketRegime.STRONG_BEAR and action == SignalAction.AL:
        conf -= 20
        notes.append("bear_regime_penalty")
    if regime in {MarketRegime.BULL, MarketRegime.STRONG_BULL} and action == SignalAction.AL:
        conf += 8
        notes.append("bull_align")
    # anomaly: RSI extreme vs MACD disagreement
    if ind.rsi14 > 75 and ind.macd_hist > 0:
        notes.append("overbought_momentum")
        conf -= 4
    conf = max(5.0, min(95.0, conf))
    return round(conf, 1), ",".join(notes) or "neutral"


def classify_news_sentiment_stub(headline: str | None = None) -> float:
    """Placeholder for KAP/news NLP (-1..+1). Neutral until wired."""
    if not headline:
        return 0.0
    text = headline.lower()
    if any(w in text for w in ("rekor", "kâr", "temettü", "büyüme")):
        return 0.35
    if any(w in text for w in ("zarar", "soruşturma", "ceza", "iflas")):
        return -0.45
    return 0.0
