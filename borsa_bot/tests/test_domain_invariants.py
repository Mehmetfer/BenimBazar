"""Silent domain invariants — no traceback required; wrong state must fail-closed.

These catch logic errors that pass syntax/lint but would produce unsafe trades.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from config.models import OrderRequest
from config.settings import settings
from crypto.market import MarketType
from crypto.providers.paribu import RequiredCryptoProvider
from crypto.reliability import crypto_signals_permitted
from crypto.safety import gate_crypto_provider
from data.integrity import DataSourceKind
from data.providers import RequiredLiveProvider, SimulatedProvider
from data.validation import AppEnvironment, gate_provider_instance
from strategy.service import TradingService


def test_inv_live_broker_env_locked():
    assert settings.live_broker_enabled is False
    assert settings.live_confirmed is False


def test_inv_live_broker_adapter_cannot_submit():
    from execution.broker_adapter import LiveBrokerDisabled

    broker = LiveBrokerDisabled()
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=10.0, reason="inv")
    result = broker.submit(order, "X")
    assert result.ok is False
    assert result.status == "BLOCKED"


def test_inv_missing_provider_blocks_signals_production():
    blocked = gate_provider_instance(RequiredLiveProvider("offline"), AppEnvironment.PRODUCTION)
    assert blocked.signals_allowed is False


def test_inv_simulated_never_live_ready():
    p = SimulatedProvider()
    meta = p.source_meta()
    assert meta.kind == DataSourceKind.SIMULATED
    assert meta.live_ready is False


def test_inv_crypto_disabled_no_trade_signals():
    gate = gate_crypto_provider(
        RequiredCryptoProvider("off"),
        app_env=AppEnvironment.DEVELOPMENT,
        crypto_enabled=False,
    )
    assert gate.signals_allowed is False
    assert gate.ok is False


def test_inv_crypto_required_provider_no_market_data():
    p = RequiredCryptoProvider("NO_DATA")
    assert p.has_market_data() is False
    assert p.list_symbols() == []


def test_inv_bist_scan_not_crypto_market_type():
    svc = TradingService()
    for d in svc.scan()[:5]:
        mt = getattr(d, "market_type", None)
        if mt is not None:
            assert str(mt).upper() != "CRYPTO"


def test_inv_market_type_parse_defaults_bist():
    assert MarketType.parse(None) == MarketType.BIST
    assert MarketType.parse("CRYPTO") == MarketType.CRYPTO


def test_inv_kill_switch_blocks_pretrade(monkeypatch):
    from autonomous.gates import evaluate_pretrade_gates

    trading = TradingService()
    monkeypatch.setattr("autonomous.gates.settings", replace(settings, kill_switch=True))

    class D:
        symbol = "THYAO"
        decision = type("X", (), {"value": "BUY"})()
        signal = type("X", (), {"value": "AL"})()
        risk_verdict = "APPROVE"
        stop_price = 95
        target_price = 110
        trade_plan = None
        ai_trade_plan = None

    assert evaluate_pretrade_gates(trading, D()).passed is False


def test_inv_empty_risk_verdict_blocks_buy():
    from autonomous.gates import evaluate_pretrade_gates

    trading = TradingService()

    class D:
        symbol = "THYAO"
        decision = type("X", (), {"value": "BUY"})()
        signal = type("X", (), {"value": "AL"})()
        risk_verdict = ""
        stop_price = 95
        target_price = 110
        trade_plan = None
        ai_trade_plan = None

    assert evaluate_pretrade_gates(trading, D()).passed is False


def test_inv_stale_live_badge_not_live():
    from crypto.dashboard import live_status_badge

    stale = datetime.now(timezone.utc) - timedelta(seconds=600)
    assert live_status_badge(has_quote=True, data_source_kind="LIVE", ts=stale, max_age_sec=30) == "STALE"


def test_inv_simulated_badge_never_live():
    from crypto.dashboard import live_status_badge

    now = datetime.now(timezone.utc)
    assert live_status_badge(has_quote=True, data_source_kind="SIMULATED", ts=now) == "UNAVAILABLE"


def test_inv_crypto_unknown_symbol_chart_empty_not_crash():
    from crypto.service import CryptoFoundationService

    svc = CryptoFoundationService()
    chart = svc.chart("NOT_A_REAL_PAIR_ZZZ", timeframe="15m")
    assert isinstance(chart, dict)
    assert chart.get("count", 0) == 0 or chart.get("candles") == [] or chart.get("ok") is False


def test_inv_ai_confidence_not_calibrated_probability():
    from decision.engine import AIDecisionEngine

    out = AIDecisionEngine(TradingService()).run_from_scan_rows(
        [{"symbol": "THYAO", "final_decision": "WAIT", "scores": {}, "mtf": {}, "opportunity": {}}],
        market_type="BIST",
    )
    card = out.get("top_card") or {}
    assert card.get("calibrated_probability") is None


def test_inv_unreliable_crypto_blocks_signal_emission():
    class Bad:
        def has_market_data(self):
            return False

        def is_fresh(self, max_age_sec: float = 30.0):
            return False

        kind = DataSourceKind.UNAVAILABLE

    ok, reason = crypto_signals_permitted(Bad(), crypto_enabled=True, signals_enabled=True)
    assert ok is False
    assert reason


def test_inv_fresh_live_crypto_permits_when_flags_on():
    class Good:
        def has_market_data(self):
            return True

        def is_fresh(self, max_age_sec: float = 30.0):
            return True

        kind = DataSourceKind.LIVE

    ok, reason = crypto_signals_permitted(Good(), crypto_enabled=True, signals_enabled=True)
    assert ok is True
    assert reason == "OK"
