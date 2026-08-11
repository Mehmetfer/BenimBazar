"""Phase 2 — real MD readiness, universe, paper FSM, auth, prediction isolation."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from alerts.status import channel_status_report
from auth import AuthStore, Role, auth_store
from config.models import OrderRequest
from config.settings import settings
from data.http_live import HttpLiveMarketDataProvider
from data.providers import HttpLiveProviderStub, classify_provider, create_provider
from execution.paper import PaperBroker, PaperOrderState
from portfolio.ledger import PortfolioLedger
from prediction.store import PredictionStore
from universe.bist100 import list_companies
from universe.tradeable import list_tradeable, universe_stats


def test_tradeable_universe_full_and_separate_from_xu100():
    stats = universe_stats()
    assert stats["full_universe"] >= 400
    assert stats["xu100_members"] == 100
    assert len(list_companies()) == 100
    inst = list_tradeable()
    assert any(i.xu100 for i in inst)
    assert any(not i.xu100 for i in inst)


def test_http_live_provider_fail_closed_without_server():
    p = HttpLiveMarketDataProvider("http://127.0.0.1:9", "token", timeout_sec=0.2)
    p.tick()
    assert p.has_market_data() is False
    assert classify_provider(p) == "REAL"  # adapter is real class, not stub
    with pytest.raises(RuntimeError):
        p.get_quote("THYAO")


def test_create_provider_live_returns_http_live_not_stub(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MARKET_DATA_TOKEN", "test-token")
    # Bypass production gate via DEVELOPMENT
    p = create_provider("live")
    assert isinstance(p, HttpLiveMarketDataProvider)
    assert not isinstance(p, HttpLiveProviderStub)


def test_paper_fsm_full_fill_default(tmp_path: Path):
    ledger = PortfolioLedger(db_path=tmp_path / "paper1.db")
    broker = PaperBroker(ledger)
    res = broker.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=10, price=100, reason="t", client_order_id="c1"),
        "ULASTIRMA",
    )
    assert res.ok
    assert res.status == PaperOrderState.FILLED.value
    assert res.quantity == 10


def test_paper_partial_fill_and_cancel(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "execution.paper.settings",
        replace(settings, paper_partial_fill_pct=0.4, paper_cancel_race_fill_pct=0.0),
    )
    ledger = PortfolioLedger(db_path=tmp_path / "paper2.db")
    broker = PaperBroker(ledger)
    res = broker.submit(
        OrderRequest(symbol="GARAN", side="BUY", quantity=1000, price=50, reason="t", client_order_id="partial-1"),
        "BANKA",
    )
    assert res.ok
    assert res.status == PaperOrderState.PARTIALLY_FILLED.value
    assert abs((res.quantity or 0) - 400) < 1e-6
    order = broker.get_order("partial-1")
    assert order is not None
    assert abs(order.remaining - 600) < 1e-6
    cancel = broker.cancel("partial-1")
    assert cancel.ok
    assert cancel.status == PaperOrderState.CANCELLED.value
    assert broker.get_order("partial-1") is None or broker.open_orders.get("partial-1") is None


def test_paper_duplicate_client_order_id(tmp_path: Path):
    ledger = PortfolioLedger(db_path=tmp_path / "paper3.db")
    broker = PaperBroker(ledger)
    # Force remaining open via partial
    from dataclasses import replace as _r

    import execution.paper as paper_mod

    paper_mod.settings = _r(settings, paper_partial_fill_pct=0.5)
    try:
        broker.submit(
            OrderRequest(symbol="ASELS", side="BUY", quantity=100, price=10, reason="t", client_order_id="dup-x"),
            "SAVUNMA",
        )
        res2 = broker.submit(
            OrderRequest(symbol="ASELS", side="BUY", quantity=100, price=10, reason="t", client_order_id="dup-x"),
            "SAVUNMA",
        )
        assert res2.ok is False
        assert res2.status == "DUPLICATE"
    finally:
        paper_mod.settings = settings


def test_notification_channel_status_honest():
    rep = channel_status_report()
    assert set(rep["channels"]) >= {"PUSH", "SOUND", "TTS", "SMS", "IN_APP"}
    assert rep["placeholders_are_not_deliveries"] is True
    for v in rep["channels"].values():
        assert v in {"ENABLED", "DISABLED", "NOT_CONFIGURED", "ERROR"}


def test_auth_roles(tmp_path: Path):
    store = AuthStore(path=tmp_path / "auth.json")
    # inject user
    import hashlib
    import json

    tok = "test-admin-token-xyz"
    store.path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "admin",
                        "role": "ADMIN",
                        "token_hash": hashlib.sha256(tok.encode()).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ctx = store.authenticate_token(tok)
    assert ctx is not None
    assert ctx.role is Role.ADMIN
    login = store.login("admin", tok)
    assert login["ok"] is True
    assert "session_token" in login


def test_prediction_market_type_filter(tmp_path: Path):
    store = PredictionStore(path=tmp_path / "pred.db")
    from prediction.models import HorizonForecast, PredictionRecord, TimeHorizon

    def _rec(mtype: str, sym: str) -> PredictionRecord:
        return PredictionRecord(
            prediction_id=f"p-{mtype}",
            timestamp="2026-01-01T00:00:00+00:00",
            symbol=sym,
            price_at_prediction=100,
            signal="BUY",
            confidence=70,
            probability=0.5,
            entry_price=100,
            stop_loss=95,
            target_1=105,
            target_2=110,
            target_3=115,
            strategy="test",
            market_regime="BULL",
            sector="TEST",
            time_horizon_primary="1H",
            model_version="1.0.0",
            strategy_version="1.0.0",
            features_snapshot={},
            forecasts=[
                HorizonForecast(
                    horizon=TimeHorizon.H1.value,
                    direction="UP",
                    forecast_return_pct=1.0,
                    forecast_price=101,
                    low_return_pct=0.5,
                    base_return_pct=1.0,
                    high_return_pct=1.5,
                    probability=0.55,
                    confidence=70,
                    uncertainty="MEDIUM",
                )
            ],
            market_type=mtype,
            data_source_kind="SIMULATED",
            market_data_source="SIMULATED",
            prediction_source="TEST",
        )

    store.insert_prediction(_rec("BIST", "THYAO"))
    store.insert_prediction(_rec("CRYPTO", "BTC_TL"))
    bist = store.recent_predictions(limit=10, market_type="BIST")
    crypto = store.recent_predictions(limit=10, market_type="CRYPTO")
    assert all(r.get("market_type", "BIST").upper() == "BIST" for r in bist)
    assert all(r.get("market_type", "").upper() == "CRYPTO" for r in crypto)
    assert {r["symbol"] for r in bist} == {"THYAO"}
    assert {r["symbol"] for r in crypto} == {"BTC_TL"}


def test_api_phase2_endpoints():
    from fastapi.testclient import TestClient
    from dashboard.app import app

    client = TestClient(app)
    uni = client.get("/api/universe").json()
    assert uni["full_universe"] >= 400
    assert uni["xu100_members"] == 100
    notif = client.get("/api/notifications/status").json()
    assert "channels" in notif
    auth = client.get("/api/auth/status").json()
    assert "auth_enabled" in auth
    audit = client.get("/api/phase2/audit").json()
    assert audit["LIVE"] in {"DISABLED", "DRY-RUN", "ENABLED_FLAG_ONLY"}
    assert audit["FULL_UNIVERSE"] >= 400
    assert audit["SYMBOL_DISCOVERY"] == "FULL"


def test_engine_reports_universe_not_confused_with_top_display():
    from autonomous.engine import AutonomousTradingEngine
    from autonomous.audit import AutonomyAuditLog
    from autonomous.events import AutonomyEventLog
    from autonomous.mode_store import AutonomyModeStore
    from autonomous.scheduler import CycleSchedulerGuard
    from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled
    from strategy.service import TradingService

    tmp = Path("/tmp/phase2_engine_test")
    tmp.mkdir(exist_ok=True)
    trading = TradingService()
    eng = AutonomousTradingEngine(
        trading=trading,
        audit=AutonomyAuditLog(path=tmp / "a.db"),
        events=AutonomyEventLog(path=tmp / "e.db"),
        scheduler=CycleSchedulerGuard(),
        modes=AutonomyModeStore(path=tmp / "m.json"),
        router=ExecutionRouter(paper=trading.broker, live=LiveBrokerDisabled()),
    )
    eng.modes.set("SEMI_AUTO")
    report = eng.run_cycle("BIST", force=True)
    filt = report.get("filter_stats") or {}
    assert filt.get("FULL_MARKET_UNIVERSE", 0) >= 400
    assert filt.get("WITH_MARKET_DATA", 0) < filt.get("FULL_MARKET_UNIVERSE", 0)
    assert filt.get("TOP_DISPLAY", 10) <= 10
