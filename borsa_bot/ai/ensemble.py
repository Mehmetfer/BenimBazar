from __future__ import annotations

from dataclasses import dataclass

from config.models import MarketRegime, SignalAction
from engines.long_term import HorizonOpportunity


@dataclass
class SpecialistScores:
    technical: float
    fundamental: float
    momentum: float
    value: float
    quality: float
    news: float
    market: float
    risk: float
    anomaly: float

    def as_dict(self) -> dict[str, float]:
        return self.__dict__.copy()


def build_specialists(
    *,
    technical: float,
    fundamental: float,
    momentum: float,
    value: float,
    quality: float,
    news: float,
    market: float,
    risk_safety: float,
    anomaly_penalty: float,
) -> SpecialistScores:
    return SpecialistScores(
        technical=technical,
        fundamental=fundamental,
        momentum=momentum,
        value=value,
        quality=quality,
        news=news,
        market=market,
        risk=risk_safety,
        anomaly=max(0, 100 - anomaly_penalty),
    )


def meta_decision(
    specs: SpecialistScores,
    *,
    regime: MarketRegime,
    horizon_ops: list[HorizonOpportunity],
) -> tuple[SignalAction, float, str]:
    """
    Weighted meta engine — not a simple average.
    Risk & market can veto; specialists inform ranking only.
    """
    if regime == MarketRegime.STRONG_BULL:
        w = dict(technical=0.18, momentum=0.18, quality=0.12, fundamental=0.1, value=0.08, market=0.15, news=0.05, risk=0.1, anomaly=0.04)
    elif regime == MarketRegime.NEUTRAL:
        w = dict(technical=0.12, momentum=0.1, quality=0.15, fundamental=0.12, value=0.15, market=0.1, news=0.06, risk=0.15, anomaly=0.05)
    elif regime in {MarketRegime.BEAR, MarketRegime.STRONG_BEAR}:
        w = dict(technical=0.08, momentum=0.05, quality=0.2, fundamental=0.15, value=0.12, market=0.15, news=0.05, risk=0.15, anomaly=0.05)
    else:
        w = dict(technical=0.15, momentum=0.15, quality=0.12, fundamental=0.1, value=0.1, market=0.12, news=0.06, risk=0.12, anomaly=0.08)

    d = specs.as_dict()
    score = sum(d[k] * w[k] for k in w)
    # Horizon agreement bonus
    buys = sum(1 for h in horizon_ops if h.decision in {SignalAction.BUY, SignalAction.STRONG_BUY})
    if buys >= 2:
        score += 4
    if specs.risk < 40 or specs.anomaly < 40:
        return SignalAction.NO_TRADE, round(score, 1), "risk_or_anomaly_veto"
    if specs.market < 35:
        return SignalAction.WAIT, round(score, 1), "weak_market"
    if score >= 88 and buys >= 1:
        return SignalAction.STRONG_BUY, round(score, 1), "meta_strong_confluence"
    if score >= 78 and buys >= 1:
        return SignalAction.BUY, round(score, 1), "meta_buy"
    if score >= 65:
        return SignalAction.WATCH, round(score, 1), "meta_watch"
    if score < 45:
        return SignalAction.NO_TRADE, round(score, 1), "meta_avoid"
    return SignalAction.WAIT, round(score, 1), "meta_wait"
