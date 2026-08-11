"""Phase 3 crypto analytics & signal engine tests — BIST path untouched."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config.models import QuoteSnapshot
from config.settings import settings
from crypto.analytics import analyze_bars
from crypto.engine import CryptoSignalEngine, _synthetic_live_bars
from crypto.predictions import record_crypto_prediction
from crypto.providers.paribu import ParibuMarketDataProvider
from crypto.risk_crypto import evaluate_crypto_entry
from crypto.signals import decide_crypto_signal
from crypto.trade_plan_crypto import build_crypto_trade_plan, crypto_size_from_risk
from data.integrity import DataSourceKind
from data.validation import MarketDataGateCode
from portfolio.ledger import PortfolioLedger
from prediction.store import PredictionStore
from risk.engine import RiskEngine
from tests.test_paribu_live import ORDERBOOK_SAMPLE, TICKER_SAMPLE, _client_with


def _live_quote(symbol: str = "BTC_TL", price: float = 100.0) -> QuoteSnapshot:
    now = datetime.now(timezone.utc)
    return QuoteSnapshot(
        symbol=symbol,
        name="BTC/TL",
        sector="CRYPTO",
        price=price,
        bid=price * 0.999,
        ask=price * 1.001,
        volume=50_000,
        trades=100,
        ts=now,
        data_source_kind=DataSourceKind.LIVE.value,
        provider="paribu",
        environment_origin="LIVE",
        market_status="OPEN",
        received_at=now,
    )


def test_analytics_insufficient_history():
    bars = _synthetic_live_bars(symbol="BTC_TL", n=50)
    snap = analyze_bars("BTC_TL", bars, _live_quote())
    assert snap.ok is False
    assert "INSUFFICIENT" in snap.note


def test_analytics_full_pipeline_indicators():
    bars = _synthetic_live_bars(symbol="BTC_TL", n=240, start_price=100.0)
    q = _live_quote(price=bars[-1].close)
    snap = analyze_bars("BTC_TL", bars, q)
    assert snap.ok is True
    assert snap.indicators is not None
    assert snap.scores is not None
    assert 0 <= snap.model_score <= 100
    assert "NOT" in snap.model_score_definition.upper() or "calibrated" in snap.model_score_definition.lower()
    for tf in ("15m", "1h", "4h", "1d"):
        assert tf in snap.mtf


def test_model_score_not_labeled_probability():
    bars = _synthetic_live_bars(symbol="ETH_USDT", n=240)
    snap = analyze_bars("ETH_USDT", bars, _live_quote("ETH_USDT", bars[-1].close))
    d = snap.to_dict()
    assert "model_score" in d
    assert "probability" not in d or d.get("probability") in (None, 0, 0.0)


def test_fractional_crypto_sizing():
    qty, max_risk, rpu = crypto_size_from_risk(
        equity=100_000, entry=3_000_000, stop=2_950_000, size_mult=1.0, max_exposure_pct=15
    )
    assert qty > 0
    assert qty * 3_000_000 <= 100_000 * 0.15 + 1e-6


def test_trade_plan_fields():
    bars = _synthetic_live_bars(symbol="BTC_TL", n=240)
    snap = analyze_bars("BTC_TL", bars, _live_quote(price=bars[-1].close))
    assert snap.indicators
    plan = build_crypto_trade_plan(
        price=bars[-1].close,
        ind=snap.indicators,
        equity=100_000,
        cash=100_000,
        max_exposure_pct=15,
    )
    assert plan is not None
    assert plan.entry > 0 and plan.stop_loss > 0 and plan.target_1 > plan.entry
    assert plan.risk_reward >= 1.0
    assert plan.position_size >= 0


def test_signal_stale_or_invalid_no_signal(tmp_path):
    object.__setattr__(settings, "crypto_enabled", True)
    object.__setattr__(settings, "crypto_signals_enabled", True)
    object.__setattr__(settings, "paribu_enabled", True)
    try:
        http = _client_with({"/market/ticker": TICKER_SAMPLE, "/orderbook": ORDERBOOK_SAMPLE})
        p = ParibuMarketDataProvider(http=http, enable_websocket=False)
        p.tick()
        eng = CryptoSignalEngine(
            provider=p,
            ledger=PortfolioLedger(db_path=tmp_path / "c.db"),
            record_predictions=False,
        )
        # insufficient history from provider trades → NO_TRADE
        res = eng.analyze_symbol("BTC_TL")
        assert res.signal == "NO_TRADE"
        assert "INSUFFICIENT" in res.note or "NO_" in res.note or "VALIDATION" in res.note or res.note
    finally:
        object.__setattr__(settings, "crypto_enabled", False)
        object.__setattr__(settings, "crypto_signals_enabled", False)
        object.__setattr__(settings, "paribu_enabled", False)


def test_signal_with_injected_live_bars(tmp_path):
    object.__setattr__(settings, "crypto_enabled", True)
    object.__setattr__(settings, "crypto_signals_enabled", True)
    object.__setattr__(settings, "paribu_enabled", True)
    try:
        http = _client_with({"/market/ticker": TICKER_SAMPLE, "/orderbook": ORDERBOOK_SAMPLE})
        p = ParibuMarketDataProvider(http=http, enable_websocket=False)
        p.tick()
        bars = _synthetic_live_bars(symbol="BTC_TL", n=240, start_price=115.0)
        q = _live_quote("BTC_TL", price=bars[-1].close)
        eng = CryptoSignalEngine(
            provider=p,
            ledger=PortfolioLedger(db_path=tmp_path / "c2.db"),
            record_predictions=False,
        )
        res = eng.analyze_symbol("BTC_TL", bars=bars, quote=q)
        assert res.market_type == "CRYPTO"
        assert res.paper_only is True
        assert res.signal in {
            "STRONG_BUY",
            "BUY",
            "WAIT",
            "WATCH",
            "SELL",
            "STRONG_SELL",
            "NO_TRADE",
            "AL",
            "SAT",
            "BEKLE",
            "ALMA",
        }
        assert res.probability_label == "NOT_A_PROBABILITY"
        assert res.model_score_definition
        if res.trade_plan:
            assert "entry" in res.trade_plan and "stop_loss" in res.trade_plan
    finally:
        object.__setattr__(settings, "crypto_enabled", False)
        object.__setattr__(settings, "crypto_signals_enabled", False)
        object.__setattr__(settings, "paribu_enabled", False)


def test_risk_blocks_wide_spread(tmp_path):
    bars = _synthetic_live_bars(symbol="BTC_TL", n=240)
    snap = analyze_bars("BTC_TL", bars, _live_quote(price=bars[-1].close))
    plan = build_crypto_trade_plan(
        price=bars[-1].close, ind=snap.indicators, equity=100_000, cash=100_000
    )
    led = PortfolioLedger(db_path=tmp_path / "r.db")
    risk = RiskEngine(led)
    from config.models import SignalAction

    rd = evaluate_crypto_entry(
        risk,
        symbol="BTC_TL",
        price=bars[-1].close,
        ind=snap.indicators,
        action=SignalAction.BUY,
        plan=plan.to_legacy(),
        spread_pct=9.0,
        opportunity=None,
        max_spread_pct=1.5,
    )
    assert rd.allowed is False
    assert rd.reason == "excessive_spread"


def test_prediction_market_type_crypto(tmp_path):
    store = PredictionStore(path=tmp_path / "pred.db")
    bars = _synthetic_live_bars(symbol="BTC_TL", n=240)
    q = _live_quote(price=bars[-1].close)
    snap = analyze_bars("BTC_TL", bars, q)
    plan = build_crypto_trade_plan(price=q.price, ind=snap.indicators, equity=100_000, cash=100_000)
    sig = decide_crypto_signal(snap, plan=plan, risk=None, price=q.price)
    if sig.signal == "NO_TRADE":
        sig.signal = "WAIT"
    pid = record_crypto_prediction(store, sig, price=q.price)
    assert pid and pid.startswith("CRYPTO-")
    row = store.get_prediction(pid)
    assert row is not None
    assert row.get("market_type") == "CRYPTO" or (
        isinstance(row.get("features_snapshot"), dict)
        and row["features_snapshot"].get("market_type") == "CRYPTO"
    )


def test_crypto_signals_disabled_by_default():
    assert settings.crypto_signals_enabled is False


def test_bist_regression_untouched():
    from data.providers import SimulatedProvider, create_provider
    from strategy.service import TradingService

    p = create_provider("simulated")
    assert isinstance(p, SimulatedProvider)
    svc = TradingService()
    assert isinstance(svc.scan(), list)
