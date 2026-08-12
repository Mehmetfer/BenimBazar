"""Live money foundation — locked by default; readiness never auto-unlocks."""

from __future__ import annotations

from config.models import OrderRequest
from config.settings import settings
from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled, build_execution_router
from execution.live_factory import live_adapter_status, resolve_live_adapter
from execution.paper import PaperBroker
from portfolio.ledger import PortfolioLedger
from trading_safety.live_readiness import evaluate_live_money_readiness


def test_defaults_keep_live_locked():
    assert settings.live_broker_enabled is False
    assert settings.live_confirmed is False
    assert getattr(settings, "live_dry_run", True) is True
    assert str(getattr(settings, "live_broker_adapter", "disabled")).lower() in {"disabled", "none", "stub", ""}


def test_factory_returns_disabled_by_default():
    adapter = resolve_live_adapter()
    assert isinstance(adapter, LiveBrokerDisabled)
    st = live_adapter_status()
    assert st["real_adapter_loaded"] is False
    assert st["live_broker_enabled"] is False


def test_router_live_mode_blocked_without_flags(tmp_path):
    paper = PaperBroker(PortfolioLedger(db_path=tmp_path / "p.db"))
    router = build_execution_router(paper)
    order = OrderRequest(
        symbol="THYAO",
        side="BUY",
        quantity=1,
        price=100.0,
        reason="live_foundation_test",
        client_order_id="LIVE-FOUNDATION-TEST-1",
    )
    result = router.submit(order, "Havacılık", execution_mode="LIVE")
    assert result.ok is False
    assert result.status == "BLOCKED"


def test_readiness_not_verified_and_not_ready():
    report = evaluate_live_money_readiness(market_data_ok=True)
    assert report.ready is False
    assert report.live_money_readiness == "NOT VERIFIED"
    assert report.verdict in {"FOUNDATION_ONLY", "NOT_READY", "READY_PENDING_HUMAN"}
    assert any(c.id == "adapter_configured" for c in report.checks)
    body = report.to_dict()
    assert "unlock_recipe" in body
    assert len(body["unlock_recipe"]) >= 5


def test_live_readiness_api():
    from fastapi.testclient import TestClient

    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/live/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ready"] is False
    assert body["live_money_readiness"] == "NOT VERIFIED"
    assert body["flags"]["LIVE_BROKER_ENABLED"] is False

    s = client.get("/api/live/status")
    assert s.status_code == 200
    assert s.json()["live_trading"] is False
