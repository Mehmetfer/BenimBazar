from __future__ import annotations

from config.models import utc_now
from prediction.models import HorizonEvaluation, TradePlanOutcome


def direction_from_return(ret_pct: float, flat_eps: float = 0.15) -> str:
    if abs(ret_pct) < flat_eps:
        return "FLAT"
    return "UP" if ret_pct > 0 else "DOWN"


def classify_error(
    *,
    direction_correct: bool,
    return_error_pp: float,
    features: dict | None = None,
) -> str | None:
    """Objective-ish error tags only — no narrative invention."""
    if direction_correct and abs(return_error_pp) < 1.0:
        return None
    features = features or {}
    if features.get("false_breakout"):
        return "FALSE_BREAKOUT"
    if features.get("news_block") or features.get("news_shock"):
        return "NEWS_SHOCK"
    if features.get("regime_changed"):
        return "MARKET_REGIME_CHANGE"
    if features.get("volume_weak"):
        return "VOLUME_FAILURE"
    if not direction_correct:
        return "TREND_REVERSAL"
    if abs(return_error_pp) >= 3:
        return "MODEL_ERROR"
    return "UNEXPECTED_EVENT"


def prediction_quality_score(
    *,
    direction_correct: bool,
    forecast_return_pct: float,
    actual_return_pct: float,
    confidence: float,
    probability: float,
) -> float:
    dir_s = 100.0 if direction_correct else 0.0
    mag_err = abs(forecast_return_pct - actual_return_pct)
    mag_s = max(0.0, 100.0 - mag_err * 12.0)
    # Target-ish: if forecast magnitude sign matches and within 40% relative
    if forecast_return_pct != 0 and direction_correct:
        rel = abs(actual_return_pct / forecast_return_pct)
        tgt_s = 100.0 if 0.6 <= rel <= 1.4 else max(0.0, 100 - abs(1 - rel) * 80)
    else:
        tgt_s = 50.0 if direction_correct else 0.0
    # Calibration component: did realized outcome align with stated probability?
    realized = 1.0 if (actual_return_pct > 0 and forecast_return_pct > 0) or (
        actual_return_pct < 0 and forecast_return_pct < 0
    ) else 0.0
    cal_s = 100.0 - abs(probability - realized) * 100.0
    final = dir_s * 0.35 + tgt_s * 0.25 + mag_s * 0.25 + cal_s * 0.15
    return round(max(0.0, min(100.0, final)), 1)


def evaluate_horizon(
    *,
    prediction_id: str,
    symbol: str,
    horizon: str,
    price_at_prediction: float,
    forecast_price: float,
    forecast_return_pct: float,
    direction_forecast: str,
    actual_price: float,
    confidence: float,
    probability: float,
    strategy: str,
    market_regime: str,
    sector: str,
    model_version: str,
    features: dict | None = None,
    target_return_pct: float | None = None,
    market_data_source: str = "UNKNOWN",
    actual_result_source: str = "UNKNOWN",
) -> HorizonEvaluation:
    if price_at_prediction <= 0:
        actual_ret = 0.0
    else:
        actual_ret = (actual_price / price_at_prediction - 1.0) * 100.0
    err = actual_ret - forecast_return_pct
    dir_act = direction_from_return(actual_ret)
    correct = dir_act == direction_forecast or (
        direction_forecast == "FLAT" and dir_act == "FLAT"
    )
    # If both non-flat and same sign
    if direction_forecast in {"UP", "DOWN"} and dir_act == direction_forecast:
        correct = True
    elif direction_forecast in {"UP", "DOWN"} and dir_act != direction_forecast:
        correct = False

    target_hit = None
    if target_return_pct is not None and target_return_pct != 0:
        if target_return_pct > 0:
            target_hit = actual_ret >= target_return_pct * 0.95
        else:
            target_hit = actual_ret <= target_return_pct * 0.95

    abs_err = abs(err)
    q = prediction_quality_score(
        direction_correct=correct,
        forecast_return_pct=forecast_return_pct,
        actual_return_pct=actual_ret,
        confidence=confidence,
        probability=probability,
    )
    cat = classify_error(direction_correct=correct, return_error_pp=err, features=features)
    return HorizonEvaluation(
        prediction_id=prediction_id,
        symbol=symbol,
        horizon=horizon,
        evaluated_at=utc_now().isoformat(),
        price_at_prediction=price_at_prediction,
        forecast_price=forecast_price,
        forecast_return_pct=forecast_return_pct,
        actual_price=actual_price,
        actual_return_pct=round(actual_ret, 4),
        return_error_pp=round(err, 4),
        direction_forecast=direction_forecast,
        direction_actual=dir_act,
        direction_correct=correct,
        target_hit=target_hit,
        abs_error_pct=round(abs_err, 4),
        confidence=confidence,
        probability=probability,
        strategy=strategy,
        market_regime=market_regime,
        sector=sector,
        model_version=model_version,
        prediction_quality_score=q,
        error_category=cat,
        market_data_source=market_data_source,
        actual_result_source=actual_result_source,
        data_source_kind=market_data_source,
    )


def resolve_trade_plan_outcome(
    *,
    price_at: float,
    stop: float | None,
    t1: float | None,
    t2: float | None,
    t3: float | None,
    path_high: float,
    path_low: float,
    timed_out: bool,
) -> TradePlanOutcome:
    """Path-aware outcome using observed high/low since prediction (no invented fills)."""
    if stop is not None and path_low <= stop:
        return TradePlanOutcome.STOP_HIT
    if t3 is not None and path_high >= t3:
        return TradePlanOutcome.TARGET_3_HIT
    if t2 is not None and path_high >= t2:
        return TradePlanOutcome.TARGET_2_HIT
    if t1 is not None and path_high >= t1:
        return TradePlanOutcome.TARGET_1_HIT
    if timed_out:
        return TradePlanOutcome.TIMEOUT
    return TradePlanOutcome.OPEN
