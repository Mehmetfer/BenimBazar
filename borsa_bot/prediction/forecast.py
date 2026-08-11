from __future__ import annotations

"""Generate MODEL_FORECAST horizons. Uses only data available at prediction time (no look-ahead)."""

from config.models import IndicatorSet, MarketRegime, OpportunityMetrics, AITradePlan
from prediction.models import DEFAULT_ACTIVE_HORIZONS, HorizonForecast, TimeHorizon

MODEL_VERSION = "1.0.0"
STRATEGY_VERSION = "1.0.0"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def generate_horizon_forecasts(
    *,
    price: float,
    ind: IndicatorSet,
    signal: str,
    confidence: float,
    opp: OpportunityMetrics | None,
    plan: AITradePlan | None,
    regime: MarketRegime,
    horizons: tuple[TimeHorizon, ...] = DEFAULT_ACTIVE_HORIZONS,
) -> list[HorizonForecast]:
    """
    Heuristic multi-horizon forecast from ATR/momentum/EV/signal.
    Labeled MODEL_FORECAST — not a promise. No future bars used.
    """
    atr_pct = (ind.atr14 / price * 100) if price > 0 else 2.0
    mom = ind.momentum10
    side = (signal or "").upper()
    bullish = side in {"STRONG_BUY", "BUY", "AL", "WAIT_FOR_ENTRY"}
    bearish = side in {"STRONG_SELL", "SELL", "SAT"}
    base_ev = opp.expected_return_pct if opp and opp.expected_return_pct else atr_pct * 0.8
    p_win = opp.p_win if opp else max(0.4, confidence / 100.0 * 0.9)

    # Horizon scale factors (shorter = smaller move, higher confidence)
    scales = {
        TimeHorizon.H1: 0.15,
        TimeHorizon.H3: 0.30,
        TimeHorizon.D1: 0.55,
        TimeHorizon.D3: 0.85,
        TimeHorizon.W1: 1.15,
        TimeHorizon.M1: 1.8,
        TimeHorizon.M3: 2.6,
        TimeHorizon.M6: 3.4,
        TimeHorizon.Y1: 4.2,
    }
    conf_decay = {
        TimeHorizon.H1: 1.00,
        TimeHorizon.H3: 0.96,
        TimeHorizon.D1: 0.92,
        TimeHorizon.D3: 0.86,
        TimeHorizon.W1: 0.78,
        TimeHorizon.M1: 0.70,
        TimeHorizon.M3: 0.62,
        TimeHorizon.M6: 0.55,
        TimeHorizon.Y1: 0.48,
    }

    # Regime dampener
    regime_mult = {
        MarketRegime.STRONG_BULL: 1.15,
        MarketRegime.BULL: 1.05,
        MarketRegime.NEUTRAL: 0.85,
        MarketRegime.BEAR: 0.75,
        MarketRegime.STRONG_BEAR: 0.65,
    }.get(regime, 0.9)

    sign = 1.0 if bullish else (-1.0 if bearish else (1.0 if mom >= 0 else -1.0))
    if not bullish and not bearish:
        # Neutral/wait — small forecast toward structure
        sign = 1.0 if ind.structure == "HH_HL" else (-1.0 if ind.structure == "LH_LL" else 0.0)

    out: list[HorizonForecast] = []
    for h in horizons:
        scale = scales.get(h, 0.5)
        move = sign * abs(base_ev) * scale * regime_mult
        # Blend ATR path uncertainty
        band = max(0.3, atr_pct * scale * 0.55)
        low = move - band
        high = move + band
        base = move
        # Soft clamp extreme nonsense
        base = _clamp(base, -25.0, 25.0)
        low = _clamp(low, -30.0, 30.0)
        high = _clamp(high, -30.0, 30.0)
        if low > high:
            low, high = high, low
        fprice = round(price * (1 + base / 100.0), 4)
        conf_h = _clamp(confidence * conf_decay.get(h, 0.8), 5.0, 95.0)
        # Horizon probability decays; still CURRENT FORECAST PROBABILITY not historical accuracy
        prob = _clamp(p_win * conf_decay.get(h, 0.8), 0.05, 0.95)
        if abs(base) < 0.15:
            direction = "FLAT"
        elif base > 0:
            direction = "UP"
        else:
            direction = "DOWN"
        unc = "LOW" if band < 1.0 else ("MEDIUM" if band < 2.5 else "HIGH")
        # Prefer plan target alignment for D1 when available
        if plan and h == TimeHorizon.D1 and plan.target1 and price > 0:
            t_ret = (plan.target1.price - price) / price * 100
            if bullish and t_ret > 0:
                base = 0.6 * base + 0.4 * t_ret
                fprice = round(price * (1 + base / 100.0), 4)
        out.append(
            HorizonForecast(
                horizon=h.value,
                direction=direction,
                forecast_return_pct=round(base, 3),
                forecast_price=fprice,
                low_return_pct=round(low, 3),
                base_return_pct=round(base, 3),
                high_return_pct=round(high, 3),
                probability=round(prob, 4),
                confidence=round(conf_h, 1),
                uncertainty=unc,
            )
        )
    return out
