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
    conflict: bool = False,
    mtf: dict[str, str] | None = None,
) -> tuple[float, str]:
    """AI layer: quality/confidence only — never final trade permission."""
    conf = 50.0
    notes: list[str] = []
    score = buy_score if action in {SignalAction.AL, SignalAction.ALMA, SignalAction.BEKLE, SignalAction.BUY} else sell_score
    conf += min(20, abs(score - 50) * 0.4)
    if ind.adx14 >= 20:
        conf += 8
        notes.append("trend_strength_ok")
    else:
        conf -= 5
        notes.append("weak_adx")
    if spread_pct > 0.35:
        conf -= 15
        notes.append("wide_spread")
    if conflict:
        conf -= 20
        notes.append("conflict_detected")
    if regime == MarketRegime.STRONG_BEAR and action == SignalAction.AL:
        conf -= 20
        notes.append("bear_regime_penalty")
    if regime in {MarketRegime.BULL, MarketRegime.STRONG_BULL} and action == SignalAction.AL:
        conf += 8
        notes.append("bull_align")
    if ind.rsi14 > 75 and ind.macd_hist > 0:
        notes.append("overbought_momentum_anomaly")
        conf -= 4
    if mtf:
        bulls = sum(1 for v in mtf.values() if v == "BULL")
        bears = sum(1 for v in mtf.values() if v == "BEAR")
        if bulls >= 3 and bears == 0:
            conf += 6
            notes.append("mtf_aligned")
        elif bulls and bears:
            conf -= 8
            notes.append("mtf_mixed")
    conf = max(5.0, min(95.0, conf))
    return round(conf, 1), ",".join(notes) or "neutral"


def classify_volatility_regime(atr_pct: float) -> str:
    if atr_pct >= 4.5:
        return "EXTREME"
    if atr_pct >= 3.0:
        return "HIGH"
    if atr_pct <= 1.0:
        return "LOW"
    return "NORMAL"


def classify_news_sentiment_stub(headline: str | None = None) -> float:
    if not headline:
        return 0.0
    text = headline.lower()
    if any(w in text for w in ("rekor", "kâr", "temettü", "büyüme")):
        return 0.35
    if any(w in text for w in ("zarar", "soruşturma", "ceza", "iflas")):
        return -0.45
    return 0.0
