from __future__ import annotations

import math
from typing import Sequence

from config.models import Bar, IndicatorSet


def _closes(bars: Sequence[Bar]) -> list[float]:
    return [b.close for b in bars]


def ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    total = sum(values[:period])
    out[period - 1] = total / period
    for i in range(period, len(values)):
        total += values[i] - values[i - period]
        out[i] = total / period
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
        out[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            line[i] = ema_fast[i] - ema_slow[i]
    compact = [x for x in line if x is not None]
    sig_compact = ema(compact, signal)
    signal_line: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)
    j = 0
    for i, v in enumerate(line):
        if v is None:
            continue
        s = sig_compact[j]
        signal_line[i] = s
        if s is not None:
            hist[i] = v - s
        j += 1
    return line, signal_line, hist


def bollinger(values: Sequence[float], period: int = 20, factor: float = 2.0):
    mid = sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = mid[i]
        if mean is None:
            continue
        var = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(var)
        upper[i] = mean + factor * std
        lower[i] = mean - factor * std
    return upper, mid, lower


def atr(bars: Sequence[Bar], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    if len(bars) <= period:
        return out
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
    atr_vals: list[float | None] = [None]
    seed = sum(trs[:period]) / period
    atr_vals.extend([None] * (period - 1))
    atr_vals.append(seed)
    prev = seed
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
        atr_vals.append(prev)
    return atr_vals


def adx(bars: Sequence[Bar], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    if len(bars) < period * 2:
        return out
    plus_dm = [0.0]
    minus_dm = [0.0]
    tr = [0.0]
    for i in range(1, len(bars)):
        up = bars[i].high - bars[i - 1].high
        down = bars[i - 1].low - bars[i].low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        tr.append(
            max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i - 1].close),
                abs(bars[i].low - bars[i - 1].close),
            )
        )
    atr_s = sum(tr[1 : period + 1]) / period
    plus_s = sum(plus_dm[1 : period + 1]) / period
    minus_s = sum(minus_dm[1 : period + 1]) / period
    dx_list = []
    for i in range(period + 1, len(bars)):
        atr_s = (atr_s * (period - 1) + tr[i]) / period
        plus_s = (plus_s * (period - 1) + plus_dm[i]) / period
        minus_s = (minus_s * (period - 1) + minus_dm[i]) / period
        plus_di = 100 * plus_s / atr_s if atr_s else 0
        minus_di = 100 * minus_s / atr_s if atr_s else 0
        denom = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / denom if denom else 0
        dx_list.append(dx)
        if len(dx_list) >= period:
            out[i] = sum(dx_list[-period:]) / period
    return out


def stochastic(bars: Sequence[Bar], period_k: int = 14, period_d: int = 3):
    k_vals: list[float | None] = [None] * len(bars)
    for i in range(period_k - 1, len(bars)):
        window = bars[i - period_k + 1 : i + 1]
        hh = max(b.high for b in window)
        ll = min(b.low for b in window)
        k_vals[i] = 50.0 if hh == ll else (bars[i].close - ll) / (hh - ll) * 100
    d_vals: list[float | None] = [None] * len(bars)
    buf = []
    for i, k in enumerate(k_vals):
        if k is None:
            continue
        buf.append(k)
        if len(buf) >= period_d:
            d_vals[i] = sum(buf[-period_d:]) / period_d
    return k_vals, d_vals


def stochastic_rsi(values: Sequence[float], period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    r = rsi(values, period)
    stoch: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        window = [x for x in r[max(0, i - period + 1) : i + 1] if x is not None]
        if len(window) < period or r[i] is None:
            continue
        lo, hi = min(window), max(window)
        stoch[i] = 50.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100
    k = sma([x if x is not None else 0.0 for x in stoch], smooth_k)
    # mask where stoch was None
    k_out: list[float | None] = [None if stoch[i] is None else k[i] for i in range(len(values))]
    d_src = [x if x is not None else 0.0 for x in k_out]
    d_raw = sma(d_src, smooth_d)
    d_out: list[float | None] = [None if k_out[i] is None else d_raw[i] for i in range(len(values))]
    return k_out, d_out


def vwap(bars: Sequence[Bar]) -> list[float | None]:
    out: list[float | None] = []
    pv = 0.0
    vol = 0.0
    for b in bars:
        typical = (b.high + b.low + b.close) / 3
        pv += typical * b.volume
        vol += b.volume
        out.append(pv / vol if vol else None)
    return out


def obv(bars: Sequence[Bar]) -> list[float]:
    out = [0.0]
    for i in range(1, len(bars)):
        if bars[i].close > bars[i - 1].close:
            out.append(out[-1] + bars[i].volume)
        elif bars[i].close < bars[i - 1].close:
            out.append(out[-1] - bars[i].volume)
        else:
            out.append(out[-1])
    return out


def mfi(bars: Sequence[Bar], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    tp = [(b.high + b.low + b.close) / 3 for b in bars]
    raw = [tp[i] * bars[i].volume for i in range(len(bars))]
    for i in range(period, len(bars)):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos += raw[j]
            elif tp[j] < tp[j - 1]:
                neg += raw[j]
        out[i] = 100 if neg == 0 else 100 - (100 / (1 + pos / neg))
    return out


def cmf(bars: Sequence[Bar], period: int = 20) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    for i in range(period - 1, len(bars)):
        mfv = 0.0
        vol = 0.0
        for b in bars[i - period + 1 : i + 1]:
            denom = b.high - b.low
            mfm = 0.0 if denom == 0 else ((b.close - b.low) - (b.high - b.close)) / denom
            mfv += mfm * b.volume
            vol += b.volume
        out[i] = mfv / vol if vol else 0.0
    return out


def roc(values: Sequence[float], period: int = 12) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period, len(values)):
        prev = values[i - period]
        out[i] = ((values[i] - prev) / prev * 100) if prev else 0.0
    return out


def cci(bars: Sequence[Bar], period: int = 20) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    tp = [(b.high + b.low + b.close) / 3 for b in bars]
    for i in range(period - 1, len(bars)):
        window = tp[i - period + 1 : i + 1]
        mean = sum(window) / period
        mad = sum(abs(x - mean) for x in window) / period
        out[i] = 0.0 if mad == 0 else (tp[i] - mean) / (0.015 * mad)
    return out


def williams_r(bars: Sequence[Bar], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    for i in range(period - 1, len(bars)):
        window = bars[i - period + 1 : i + 1]
        hh = max(b.high for b in window)
        ll = min(b.low for b in window)
        out[i] = -50.0 if hh == ll else (hh - bars[i].close) / (hh - ll) * -100
    return out


def support_resistance(bars: Sequence[Bar], lookback: int = 40) -> tuple[float, float, float]:
    window = bars[-lookback:] if len(bars) >= lookback else list(bars)
    support = min(b.low for b in window)
    resistance = max(b.high for b in window)
    last = bars[-1]
    pivot = (last.high + last.low + last.close) / 3
    return support, resistance, pivot


def structure_label(bars: Sequence[Bar], lookback: int = 30) -> str:
    if len(bars) < lookback:
        return "RANGE"
    w = bars[-lookback:]
    mid = lookback // 2
    first_high = max(b.high for b in w[:mid])
    second_high = max(b.high for b in w[mid:])
    first_low = min(b.low for b in w[:mid])
    second_low = min(b.low for b in w[mid:])
    if second_high > first_high and second_low > first_low:
        return "HH_HL"
    if second_high < first_high and second_low < first_low:
        return "LH_LL"
    return "RANGE"


def compute_indicators(bars: Sequence[Bar]) -> IndicatorSet | None:
    if len(bars) < 210:
        return None
    # Indicator provenance inherits bar source; mixed families → reject
    from data.provenance import (
        MixedProvenanceError,
        assert_homogeneous_provenance,
        kind_of,
    )

    try:
        src = assert_homogeneous_provenance(
            [kind_of(b) for b in bars],
            context="indicators/OHLCV",
        )
    except MixedProvenanceError:
        return None
    closes = _closes(bars)
    volumes = [b.volume for b in bars]
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)
    e100 = ema(closes, 100)
    e200 = ema(closes, 200)
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    r = rsi(closes, 14)
    macd_line, macd_sig, macd_hist = macd(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    a = atr(bars, 14)
    adx_v = adx(bars, 14)
    k, d = stochastic(bars)
    srk, srd = stochastic_rsi(closes)
    vw = vwap(bars)
    vol_sma = sma(volumes, 20)
    mom = [None] * len(closes)
    for i in range(10, len(closes)):
        mom[i] = (closes[i] / closes[i - 10] - 1) * 100
    roc12 = roc(closes, 12)
    obv_v = obv(bars)
    mfi_v = mfi(bars, 14)
    cmf_v = cmf(bars, 20)
    cci_v = cci(bars, 20)
    will_v = williams_r(bars, 14)
    support, resistance, pivot = support_resistance(bars)
    structure = structure_label(bars)

    i = len(bars) - 1
    required = [
        e9[i], e21[i], e50[i], e100[i], e200[i], s20[i], s50[i], r[i],
        macd_line[i], macd_sig[i], macd_hist[i], bb_u[i], bb_m[i], bb_l[i],
        a[i], adx_v[i], k[i], d[i], srk[i], srd[i], vw[i], vol_sma[i],
        mom[i], roc12[i], mfi_v[i], cmf_v[i], cci_v[i], will_v[i],
    ]
    if any(v is None for v in required):
        return None
    return IndicatorSet(
        ema9=e9[i],
        ema21=e21[i],
        ema50=e50[i],
        ema100=e100[i],
        ema200=e200[i],
        sma20=s20[i],
        sma50=s50[i],
        rsi14=r[i],
        macd=macd_line[i],
        macd_signal=macd_sig[i],
        macd_hist=macd_hist[i],
        bb_upper=bb_u[i],
        bb_middle=bb_m[i],
        bb_lower=bb_l[i],
        atr14=a[i],
        adx14=adx_v[i],
        stoch_k=k[i],
        stoch_d=d[i],
        stoch_rsi_k=srk[i],
        stoch_rsi_d=srd[i],
        vwap=vw[i],
        vol_sma20=vol_sma[i],
        momentum10=mom[i],
        roc12=roc12[i],
        obv=obv_v[i],
        mfi14=mfi_v[i],
        cmf20=cmf_v[i],
        cci20=cci_v[i],
        williams_r=will_v[i],
        support=support,
        resistance=resistance,
        pivot=pivot,
        structure=structure,
        data_source_kind=src.value,
    )
