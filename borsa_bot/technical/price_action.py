from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from config.models import Bar, IndicatorSet


@dataclass
class PriceActionView:
    pattern: str
    breakout: bool
    false_breakout: bool
    retest: bool
    support_bounce: bool
    resistance_rejection: bool
    consolidation: bool
    volume_confirmed: bool
    gap: bool
    structure: str
    notes: list[str]


def detect_gap(bars: Sequence[Bar]) -> bool:
    if len(bars) < 2:
        return False
    prev, last = bars[-2], bars[-1]
    return last.low > prev.high * 1.005 or last.high < prev.low * 0.995


def is_consolidation(bars: Sequence[Bar], lookback: int = 20) -> bool:
    w = bars[-lookback:] if len(bars) >= lookback else list(bars)
    if len(w) < 10:
        return False
    hi = max(b.high for b in w)
    lo = min(b.low for b in w)
    mid = (hi + lo) / 2
    return ((hi - lo) / mid) < 0.04 if mid else False


def analyze_price_action(bars: Sequence[Bar], ind: IndicatorSet, volume: float) -> PriceActionView:
    notes: list[str] = []
    close = bars[-1].close
    breakout = close > ind.resistance * 0.999
    vol_ok = volume > ind.vol_sma20 * 1.3 if ind.vol_sma20 else False
    false_bo = False
    if len(bars) >= 3 and bars[-2].close > ind.resistance and close < ind.resistance:
        false_bo = True
        notes.append("false_breakout")
    retest = False
    if breakout and len(bars) >= 5:
        # recent touch near prior resistance from above
        for b in bars[-5:-1]:
            if abs(b.low - ind.resistance) / ind.resistance < 0.008:
                retest = True
                notes.append("retest")
                break
    support_bounce = close > ind.support and bars[-1].low <= ind.support * 1.01 and close > bars[-1].open
    resistance_rej = close < ind.resistance and bars[-1].high >= ind.resistance * 0.99 and close < bars[-1].open
    consol = is_consolidation(bars)
    gap = detect_gap(bars)
    if breakout and not vol_ok:
        notes.append("breakout_without_volume")
    if breakout and vol_ok:
        notes.append("volume_confirmed_breakout")
    pattern = "RANGE"
    if breakout and vol_ok and not false_bo:
        pattern = "BREAKOUT"
    elif support_bounce and ind.structure == "HH_HL":
        pattern = "SUPPORT_BOUNCE"
    elif resistance_rej:
        pattern = "RESISTANCE_REJECTION"
    elif consol:
        pattern = "CONSOLIDATION"
    elif ind.structure == "HH_HL":
        pattern = "TREND_CONTINUATION"
    elif ind.structure == "LH_LL":
        pattern = "TREND_REVERSAL_RISK"
    return PriceActionView(
        pattern=pattern,
        breakout=breakout,
        false_breakout=false_bo,
        retest=retest,
        support_bounce=support_bounce,
        resistance_rejection=resistance_rej,
        consolidation=consol,
        volume_confirmed=vol_ok and breakout,
        gap=gap,
        structure=ind.structure,
        notes=notes,
    )
