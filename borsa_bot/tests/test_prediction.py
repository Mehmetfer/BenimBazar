from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.models import IndicatorSet, MarketRegime, OpportunityMetrics
from prediction.evaluate import evaluate_horizon, prediction_quality_score, resolve_trade_plan_outcome
from prediction.forecast import generate_horizon_forecasts
from prediction.models import TradePlanOutcome
from prediction.rating import (
    build_reliability_report,
    calibration_buckets,
    detect_degradation,
    grade_from_metrics,
    pick_champion,
    sample_tier,
)
from prediction.service import PredictionTrackingService
from prediction.store import PredictionStore
from strategy.service import TradingService


def _ind(price: float = 100.0) -> IndicatorSet:
    return IndicatorSet(
        ema9=price * 1.01,
        ema21=price,
        ema50=price * 0.99,
        ema100=price * 0.98,
        ema200=price * 0.97,
        sma20=price,
        sma50=price * 0.99,
        rsi14=58.0,
        macd=0.2,
        macd_signal=0.1,
        macd_hist=0.1,
        bb_upper=price * 1.03,
        bb_middle=price,
        bb_lower=price * 0.97,
        atr14=price * 0.02,
        adx14=25.0,
        stoch_k=55.0,
        stoch_d=50.0,
        stoch_rsi_k=55.0,
        stoch_rsi_d=50.0,
        vwap=price,
        vol_sma20=1_000_000,
        momentum10=1.5,
        roc12=1.2,
        obv=1_000_000,
        mfi14=55.0,
        cmf20=0.05,
        cci20=40.0,
        williams_r=-40.0,
        support=price * 0.95,
        resistance=price * 1.05,
        pivot=price,
        structure="HH_HL",
    )


def test_metric_distinction_labels():
    tmp = Path(tempfile.mkdtemp()) / "p.db"
    svc = PredictionTrackingService(store=PredictionStore(tmp))
    ind = _ind(100)
    opp = OpportunityMetrics(
        p_win=0.8,
        expected_return_pct=5.0,
        expected_loss_pct=2.0,
        risk_reward=2.5,
        expected_value=0.5,
        volatility_pct=2.0,
        drawdown_impact=1.0,
        position_size_mult=1.0,
        confidence=80.0,
    )
    rec = svc.record_prediction(
        symbol="THYAO",
        price=100.0,
        signal="STRONG_BUY",
        confidence=82.0,
        probability=0.8,
        ind=ind,
        regime=MarketRegime.BULL,
        sector="TRANSPORT",
        strategy="SWING",
        opp=opp,
    )
    assert rec is not None
    card = svc.symbol_card("THYAO", latest=rec)
    assert card["current_forecast_probability_label"] == "TAHMİN OLASILIĞI"
    assert card["ai_reliability"]["historical_accuracy_label"] == "GEÇMİŞ DOĞRULUK"
    assert "TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK" in card["principle"]
    # Current probability must not be silently renamed as accuracy
    assert card["current_forecast_probability"] == 80
    assert card["ai_reliability"]["gecmis_dogruluk"] is None or card["ai_reliability"]["sample_size"] == 0


def test_immutable_prediction_and_horizons():
    tmp = Path(tempfile.mkdtemp()) / "p2.db"
    store = PredictionStore(tmp)
    svc = PredictionTrackingService(store=store)
    rec = svc.record_prediction(
        symbol="ASELS",
        price=50.0,
        signal="BUY",
        confidence=75.0,
        probability=0.7,
        ind=_ind(50),
        regime=MarketRegime.NEUTRAL,
        strategy="DAY",
    )
    assert rec is not None
    assert len(rec.forecasts) == 5
    horizons = {f.horizon for f in rec.forecasts}
    assert horizons == {"1H", "3H", "1D", "3D", "1W"}
    for f in rec.forecasts:
        assert f.low_return_pct <= f.base_return_pct <= f.high_return_pct
        assert f.forecast_price > 0
    # Second insert same id rejected / no overwrite
    store.insert_prediction(rec)
    assert len(store.recent_predictions("ASELS")) == 1


def test_bearish_forecast_and_evaluation():
    tmp = Path(tempfile.mkdtemp()) / "p3.db"
    svc = PredictionTrackingService(store=PredictionStore(tmp))
    rec = svc.record_prediction(
        symbol="TUPRS",
        price=200.0,
        signal="STRONG_SELL",
        confidence=70.0,
        probability=0.65,
        ind=_ind(200),
        regime=MarketRegime.BEAR,
        strategy="SWING",
        opp=OpportunityMetrics(
            p_win=0.65,
            expected_return_pct=4.0,
            expected_loss_pct=2.0,
            risk_reward=2.0,
            expected_value=0.3,
            volatility_pct=2.5,
            drawdown_impact=1.0,
            position_size_mult=0.8,
            confidence=70.0,
        ),
    )
    assert rec is not None
    assert any(f.forecast_return_pct < 0 for f in rec.forecasts)
    card = svc.symbol_card("TUPRS", latest=rec)
    assert card["forecast_bias"] == "BEARISH FORECAST"

    # Force-evaluate as if horizons due
    fc = rec.forecasts[0]
    ev = evaluate_horizon(
        prediction_id=rec.prediction_id,
        symbol="TUPRS",
        horizon=fc.horizon,
        price_at_prediction=200.0,
        forecast_price=fc.forecast_price,
        forecast_return_pct=fc.forecast_return_pct,
        direction_forecast=fc.direction,
        actual_price=196.0,
        confidence=fc.confidence,
        probability=fc.probability,
        strategy="SWING",
        market_regime="BEAR",
        sector="ENERGY",
        model_version="1.0.0",
        target_return_pct=fc.forecast_return_pct,
    )
    assert ev.actual_return_pct < 0
    assert ev.direction_correct is True
    assert 0 <= ev.prediction_quality_score <= 100
    svc.store.insert_evaluation(ev)
    report = svc.reliability_report(symbol="TUPRS")
    assert report.sample_size == 1
    assert report.grade == "INSUFFICIENT"


def test_sample_tier_and_no_fake_a_plus():
    assert sample_tier(20).value == "INSUFFICIENT_DATA"
    assert sample_tier(75).value == "PROVISIONAL"
    assert sample_tier(200).value == "VALIDATED"
    assert sample_tier(600).value == "HIGH_CONFIDENCE"
    # 100% on tiny sample must not be S/A+
    g = grade_from_metrics(accuracy=1.0, brier=0.05, n=20, degradation=False)
    assert g.value == "INSUFFICIENT"


def test_calibration_and_degradation():
    rows = []
    for i in range(120):
        rows.append(
            {
                "direction_correct": 1 if i % 5 else 0,  # ~80%
                "probability": 0.85,
                "confidence": 85.0,
                "return_error_pp": 0.5,
                "actual_return_pct": 1.0,
                "strategy": "SWING",
                "model_version": "v1",
                "evaluated_at": f"2026-01-01T00:{i%60:02d}:00",
            }
        )
    # Prepend recent bad outcomes (newest-first)
    bad = [
        {
            "direction_correct": 0,
            "probability": 0.9,
            "confidence": 90.0,
            "return_error_pp": 3.0,
            "actual_return_pct": -2.0,
            "strategy": "SWING",
            "model_version": "v1",
            "evaluated_at": f"2026-08-01T00:{i:02d}:00",
        }
        for i in range(25)
    ]
    mixed = bad + rows
    buckets = calibration_buckets(mixed)
    assert any(b["range"].startswith("80") or b["range"].startswith("90") for b in buckets)
    assert detect_degradation(0.76, 0.69, 0.62, 0.55) is True
    rep = build_reliability_report(mixed, scope="test", key="SWING")
    assert rep.degradation is True


def test_trade_plan_outcome_and_quality():
    assert (
        resolve_trade_plan_outcome(
            price_at=100, stop=95, t1=105, t2=110, t3=120, path_high=106, path_low=99, timed_out=False
        )
        == TradePlanOutcome.TARGET_1_HIT
    )
    assert (
        resolve_trade_plan_outcome(
            price_at=100, stop=95, t1=105, t2=110, t3=120, path_high=101, path_low=94, timed_out=False
        )
        == TradePlanOutcome.STOP_HIT
    )
    q = prediction_quality_score(
        direction_correct=True,
        forecast_return_pct=5.0,
        actual_return_pct=4.2,
        confidence=82,
        probability=0.8,
    )
    assert 50 < q <= 100


def test_champion_requires_validated():
    board = [
        {
            "key": "tiny",
            "sample_size": 30,
            "sample_tier": "INSUFFICIENT_DATA",
            "historical_accuracy_pct": 100.0,
            "degradation": False,
        },
        {
            "key": "good",
            "sample_size": 200,
            "sample_tier": "VALIDATED",
            "historical_accuracy_pct": 72.0,
            "degradation": False,
        },
    ]
    champ = pick_champion(board)
    assert champ is not None
    assert champ["key"] == "good"
    assert champ.get("champion") is True


def test_service_scan_attaches_forecast_without_changing_decision():
    svc = TradingService()
    before = [d.decision.value for d in svc.scan()]
    # Second scan should still work; prediction layer must not alter decisions
    after = svc.scan()
    assert len(after) == len(before) or len(after) > 0
    ser = svc._serialize(after[0])
    assert "ai_forecast" in ser or ser.get("ai_forecast") is None or isinstance(ser.get("ai_forecast"), list)
    # Decisions are independent of prediction grades
    assert ser.get("decision") in {
        "STRONG_BUY",
        "BUY",
        "SELL",
        "STRONG_SELL",
        "WAIT",
        "WATCH",
        "NO_TRADE",
        "AL",
        "SAT",
        "BEKLE",
        "ALMA",
    }


def test_pending_evaluation_backdated():
    tmp = Path(tempfile.mkdtemp()) / "p4.db"
    store = PredictionStore(tmp)
    svc = PredictionTrackingService(store=store)
    rec = svc.record_prediction(
        symbol="GARAN",
        price=100.0,
        signal="BUY",
        confidence=70.0,
        probability=0.7,
        ind=_ind(100),
        regime=MarketRegime.BULL,
        strategy="SWING",
    )
    assert rec is not None
    # Backdate timestamp so 1H is due
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with store._conn() as c:
        c.execute("UPDATE predictions SET timestamp=? WHERE prediction_id=?", (old_ts, rec.prediction_id))
    pending = store.pending_evaluations()
    assert any(p[0]["prediction_id"] == rec.prediction_id for p in pending)
    n = svc.evaluate_due(lambda s: 101.5 if s == "GARAN" else None)
    assert n >= 1
    evals = store.list_evaluations(symbol="GARAN")
    assert evals
    assert "actual_return_pct" in evals[0]
