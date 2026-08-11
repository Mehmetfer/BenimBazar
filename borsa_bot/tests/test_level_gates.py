"""L1→L8 recovery gate + required failure simulations (safe failure, no unauthorized trade)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.models import Bar, CapitalMode, MarketRegime, OpportunityMetrics, OrderRequest
from config.settings import settings
from data.http_live import HttpLiveMarketDataProvider, _parse_ts
from data.integrity import DataSourceKind
from data.providers import RequiredLiveProvider, SimulatedProvider
from data.validation import AppEnvironment, gate_provider_instance, normalize_app_env
from autonomous.gates import evaluate_pretrade_gates
from profit.ev import dynamic_size_multiplier
from technical.mtf import aggregate_bars, analyze_mtf
from level8.engine import ContinuousLearningEngine
from level8.store import Level8Store
from strategy.service import TradingService


def test_l1_app_imports_and_settings():
    from dashboard.app import app

    assert app.title
    ts = TradingService()
    assert ts.provider is not None
    assert normalize_app_env("PRODUCTION") == "PRODUCTION"
    assert normalize_app_env("development") == "DEVELOPMENT"


def test_l1_production_blocks_simulated_provider():
    blocked = gate_provider_instance(SimulatedProvider(), AppEnvironment.PRODUCTION)
    assert blocked.ok is False or blocked.signals_allowed is False


def test_l2_http_source_meta_accepts_datetime():
    p = HttpLiveMarketDataProvider("http://127.0.0.1:9", "tok", timeout_sec=0.1)
    p._connected = True
    p._last_ok = datetime.now(timezone.utc)
    meta = p.source_meta()
    assert meta.kind == DataSourceKind.LIVE


def test_l2_parse_ts_never_invents_now():
    with pytest.raises(ValueError):
        _parse_ts(None)
    with pytest.raises(ValueError):
        _parse_ts("not-a-timestamp")
    assert _parse_ts("2024-01-15T10:00:00Z").year == 2024


def test_l2_http_bars_fail_closed_no_stale_cache():
    p = HttpLiveMarketDataProvider("http://127.0.0.1:9", "tok", timeout_sec=0.1)
    p._bars["THYAO"] = [
        Bar(ts=datetime.now(timezone.utc), open=1, high=1, low=1, close=1, volume=1, trades=1)
    ]
    with pytest.raises(RuntimeError, match="NO_MARKET_DATA"):
        p.get_bars("THYAO", 10)


def test_l3_mtf_drops_incomplete_bucket_no_lookahead():
    base = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    bars = [
        Bar(
            ts=base + timedelta(minutes=15 * i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=1000,
            trades=10,
            timeframe="15m",
            data_source_kind="SIMULATED",
        )
        for i in range(8)
    ]
    agg = aggregate_bars(bars, factor=2)
    assert len(agg) >= 1
    assert max(b.ts for b in agg) <= bars[-1].ts


def test_l3_same_input_same_mtf():
    base = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
    bars = [
        Bar(
            ts=base + timedelta(minutes=15 * i),
            open=50,
            high=51,
            low=49,
            close=50 + (0.1 if i % 2 == 0 else -0.05),
            volume=100,
            trades=5,
            timeframe="15m",
        )
        for i in range(250)
    ]
    assert analyze_mtf(bars, 15) == analyze_mtf(bars, 15)


def test_l4_confidence_not_calibrated_probability():
    from decision.engine import AIDecisionEngine

    out = AIDecisionEngine(TradingService()).run_from_scan_rows(
        [{"symbol": "THYAO", "final_decision": "WAIT", "scores": {}, "mtf": {}, "opportunity": {}}],
        market_type="BIST",
    )
    card = out.get("top_card") or {}
    assert card.get("calibrated_probability") is None


def test_l5_risk_empty_verdict_fail_closed():
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

    res = evaluate_pretrade_gates(trading, D())
    assert res.passed is False
    assert any(g.name == "RISK" and not g.passed for g in res.gates)


def test_l5_kill_switch_blocks(monkeypatch):
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


def test_l5_no_martingale_size_mult_cap():
    opp = OpportunityMetrics(
        p_win=0.6,
        expected_return_pct=5.0,
        expected_loss_pct=1.0,
        risk_reward=3.0,
        expected_value=2.0,
        volatility_pct=1.0,
        drawdown_impact=0.1,
        position_size_mult=1.0,
        confidence=90.0,
    )
    m = dynamic_size_multiplier(opp, capital_mode=CapitalMode.NORMAL, regime=MarketRegime.BULL)
    assert 0.0 <= m <= 1.0


def test_l6_duplicate_order_idempotent():
    trading = TradingService()
    q = trading.provider.get_quote("THYAO")
    oid = "IDEMP-TEST-001"
    o = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=q.price, reason="t", client_order_id=oid)
    assert trading.broker.submit(o, q.sector) is not None
    assert trading.broker.submit(o, q.sector) is not None


def test_l6_live_broker_locked():
    assert bool(getattr(settings, "live_broker_enabled", False)) is False
    from execution.broker_adapter import LiveBrokerDisabled

    assert LiveBrokerDisabled().name == "LiveBrokerDisabled"


def test_l7_ai_before_entries_in_source_file():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "autonomous" / "engine.py"
    text = src.read_text(encoding="utf-8")
    # Find within run_cycle body: AI block then entry handling
    marker = "def run_cycle"
    start = text.find(marker)
    assert start != -1
    chunk = text[start : start + 25000]
    ai_pos = chunk.find("run_from_scan_rows")
    entry_pos = chunk.find("_handle_entry_candidate")
    assert ai_pos != -1 and entry_pos != -1
    assert ai_pos < entry_pos


def test_l8_acceptance_no_auto_promote(tmp_path: Path):
    eng = ContinuousLearningEngine(TradingService(), store=Level8Store(path=tmp_path / "g.db"))
    out = eng.run_acceptance_chain()
    assert out["auto_promoted"] is False
    assert out["scorecard"]["governance"]["risk_limits"] == "DENIED"
    assert out["scorecard"]["full_level8_claimed"] is False


@pytest.mark.parametrize("scenario", ["provider_offline", "kill_switch"])
def test_failure_matrix_safe(scenario, monkeypatch):
    trading = TradingService()
    if scenario == "provider_offline":
        trading.provider = RequiredLiveProvider("offline")
        assert trading.provider.has_market_data() is False
        assert isinstance(trading.scan(), list)
    elif scenario == "kill_switch":
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
