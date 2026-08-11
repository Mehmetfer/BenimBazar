"""Crypto prediction recording — market_type=CRYPTO, horizons 1H/3H/1D/3D/1W."""

from __future__ import annotations

import uuid

from config.models import utc_now
from config.settings import settings
from crypto.market import MarketType
from crypto.signals import CryptoSignalResult
from prediction.models import HorizonForecast, PredictionRecord, TimeHorizon
from prediction.store import PredictionStore


CRYPTO_HORIZONS = (
    TimeHorizon.H1,
    TimeHorizon.H3,
    TimeHorizon.D1,
    TimeHorizon.D3,
    TimeHorizon.W1,
)


def _forecasts(price: float, signal: str, model_score: float) -> list[HorizonForecast]:
    """Directional stubs for tracking — probability field set 0 with HIGH uncertainty.

    Honest: not calibrated. Evaluation later uses actual prices.
    """
    bias = (model_score - 50.0) / 100.0
    if signal in {"SELL", "STRONG_SELL", "SAT"}:
        bias = -abs(bias)
        direction = "DOWN"
    elif signal in {"BUY", "STRONG_BUY", "AL"}:
        bias = abs(bias)
        direction = "UP"
    else:
        bias *= 0.25
        direction = "FLAT"
    out: list[HorizonForecast] = []
    for i, h in enumerate(CRYPTO_HORIZONS):
        scale = 0.005 * (i + 1)
        ret = bias * scale * 100
        out.append(
            HorizonForecast(
                horizon=h.value,
                direction=direction,
                forecast_return_pct=round(ret, 4),
                forecast_price=round(price * (1 + ret / 100.0), 6),
                low_return_pct=round(ret - abs(ret) * 0.5 - 0.5, 4),
                base_return_pct=round(ret, 4),
                high_return_pct=round(ret + abs(ret) * 0.5 + 0.5, 4),
                probability=0.0,  # NOT calibrated — do not treat as P(win)
                confidence=float(model_score),
                uncertainty="HIGH",
            )
        )
    return out


def record_crypto_prediction(
    store: PredictionStore,
    result: CryptoSignalResult,
    *,
    price: float,
) -> str | None:
    if result.signal in {None, "", "NO_TRADE", "ALMA"}:
        return None
    pid = f"CRYPTO-{uuid.uuid4().hex[:12]}"
    plan = result.trade_plan or {}
    features = {
        "market_type": MarketType.CRYPTO.value,
        "model_score": result.model_score,
        "model_score_definition": result.model_score_definition,
        "confirmations": result.confirmations,
        "mtf": result.mtf,
        "probability_label": result.probability_label,
        "note": "confidence column stores MODEL_SCORE not calibrated probability",
    }
    rec = PredictionRecord(
        prediction_id=pid,
        timestamp=utc_now().isoformat(),
        symbol=result.symbol,
        price_at_prediction=price,
        signal=result.signal,
        confidence=result.model_score,
        probability=0.0,
        entry_price=plan.get("entry"),
        stop_loss=plan.get("stop_loss"),
        target_1=plan.get("target_1"),
        target_2=plan.get("target_2"),
        target_3=plan.get("target_3"),
        strategy="CRYPTO_MTF_V1",
        market_regime="NEUTRAL",
        sector="CRYPTO",
        time_horizon_primary=TimeHorizon.H1.value,
        model_version=settings.prediction_model_version,
        strategy_version="crypto-phase3-1",
        features_snapshot=features,
        forecasts=_forecasts(price, result.signal, result.model_score),
        is_favorite=False,
        market_data_source=result.data_source_kind or "LIVE",
        prediction_source="CRYPTO_ENGINE",
        data_source_kind=result.data_source_kind or "LIVE",
        market_type=MarketType.CRYPTO.value,
    )
    return store.insert_prediction(rec)
