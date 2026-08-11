from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from config.models import Bar, IndicatorSet
from indicators.engine import compute_indicators


TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def aggregate_bars(bars: Sequence[Bar], factor: int) -> list[Bar]:
    """Aggregate base bars into higher timeframe.

    Prefer calendar/time-bucket alignment from bar timestamps when available
    (reduces look-ahead vs naive consecutive grouping from series start).
    Incomplete final bucket is dropped (no inventing closes).
    """
    if factor <= 1:
        return list(bars)
    if not bars:
        return []

    base_minutes = 15
    # Infer base from first bar timeframe if present
    try:
        tf = str(getattr(bars[0], "timeframe", "") or "15m")
        base_minutes = TF_MINUTES.get(tf, 15)
    except Exception:  # noqa: BLE001
        base_minutes = 15
    bucket_minutes = base_minutes * factor

    # Time-bucket aggregation
    buckets: dict[int, list[Bar]] = {}
    ordered: list[int] = []
    for b in bars:
        ts = b.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        # Floor to bucket boundary (UTC minutes)
        epoch_min = int(ts.timestamp() // 60)
        bucket_id = epoch_min - (epoch_min % bucket_minutes)
        if bucket_id not in buckets:
            buckets[bucket_id] = []
            ordered.append(bucket_id)
        buckets[bucket_id].append(b)

    out: list[Bar] = []
    # Drop incomplete last bucket unless it has full factor bars
    for i, bid in enumerate(ordered):
        chunk = buckets[bid]
        is_last = i == len(ordered) - 1
        if is_last and len(chunk) < factor:
            continue
        if not chunk:
            continue
        src = getattr(chunk[-1], "data_source_kind", "UNKNOWN")
        out.append(
            Bar(
                ts=chunk[-1].ts,
                open=chunk[0].open,
                high=max(x.high for x in chunk),
                low=min(x.low for x in chunk),
                close=chunk[-1].close,
                volume=sum(x.volume for x in chunk),
                trades=sum(x.trades for x in chunk),
                data_source_kind=src,
                symbol=getattr(chunk[-1], "symbol", "") or getattr(chunk[0], "symbol", ""),
                provider=getattr(chunk[-1], "provider", ""),
                environment_origin=getattr(chunk[-1], "environment_origin", "UNKNOWN"),
                timeframe=getattr(chunk[-1], "timeframe", "15m"),
                received_at=getattr(chunk[-1], "received_at", None),
            )
        )
    return out


def trend_from_ind(ind: IndicatorSet | None) -> str:
    if ind is None:
        return "UNKNOWN"
    if ind.ema9 > ind.ema21 > ind.ema50:
        return "BULL"
    if ind.ema9 < ind.ema21 < ind.ema50:
        return "BEAR"
    return "NEUTRAL"


def analyze_mtf(base_bars: Sequence[Bar], base_tf_minutes: int = 15) -> dict[str, str]:
    """Return trend labels across timeframes. Missing TFs marked UNAVAILABLE (honest)."""
    result: dict[str, str] = {}
    for name, minutes in TF_MINUTES.items():
        if minutes < base_tf_minutes:
            result[name] = "UNAVAILABLE"  # do not invent lower TF data
            continue
        factor = max(1, minutes // base_tf_minutes)
        agg = aggregate_bars(base_bars, factor)
        if len(agg) < 60:
            result[name] = "INSUFFICIENT"
            continue
        # For higher TFs we may not have 210 bars; use relaxed computation via last available EMAs
        ind = compute_indicators(agg) if len(agg) >= 210 else None
        if ind is None and len(agg) >= 60:
            # lightweight trend from closes
            closes = [b.close for b in agg]
            short = sum(closes[-9:]) / 9
            mid = sum(closes[-21:]) / 21
            result[name] = "BULL" if short > mid else ("BEAR" if short < mid else "NEUTRAL")
        else:
            result[name] = trend_from_ind(ind) if ind else "INSUFFICIENT"
    return result


def mtf_conflict_risk(mtf: dict[str, str]) -> tuple[bool, float, str]:
    """Higher TF bearish vs lower TF bullish => conflict / risk up."""
    higher = [mtf.get(k) for k in ("1w", "1d", "4h") if mtf.get(k) not in (None, "UNAVAILABLE", "INSUFFICIENT", "UNKNOWN")]
    lower = [mtf.get(k) for k in ("1h", "30m", "15m") if mtf.get(k) not in (None, "UNAVAILABLE", "INSUFFICIENT", "UNKNOWN")]
    if not higher or not lower:
        return False, 0.0, "mtf_partial"
    higher_bear = sum(1 for x in higher if x == "BEAR")
    lower_bull = sum(1 for x in lower if x == "BULL")
    if higher_bear >= 2 and lower_bull >= 2:
        return True, 25.0, "lower_tf_bull_vs_higher_tf_bear"
    higher_bull = sum(1 for x in higher if x == "BULL")
    lower_bear = sum(1 for x in lower if x == "BEAR")
    if higher_bull >= 2 and lower_bear >= 2:
        return True, 15.0, "lower_tf_bear_vs_higher_tf_bull"
    aligned = higher_bull >= 2 and lower_bull >= 2
    return False, (-10.0 if aligned else 0.0), ("mtf_aligned_bull" if aligned else "mtf_mixed")
