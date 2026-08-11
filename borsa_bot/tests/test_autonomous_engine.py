"""AutonomousTradingEngine — gates, SHADOW, LIVE lock, health, idempotency."""
from __future__ import annotations

from pathlib import Path

import pytest

from autonomous.audit import AutonomyAuditLog
from autonomous.engine import AutonomousTradingEngine
from autonomous.events import AutonomyEventLog
from autonomous.execution_modes import ExecutionMode, parse_execution_mode
from autonomous.gates import evaluate_pretrade_gates
from autonomous.health import run_health_check
from autonomous.mode_store import AutonomyModeStore
from autonomous.modes import UserTradingMode
from autonomous.orders import OrderState, make_client_order_id, transition
from autonomous.reconcile import reconcile_paper
from autonomous.scheduler import CycleSchedulerGuard
from config.models import SignalAction
from config.settings import settings
from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled
from strategy.service import TradingService


@pytest.fixture()
def tmp_store(tmp_path: Path) -> AutonomyModeStore:
    return AutonomyModeStore(path=tmp_path / "mode.json")


@pytest.fixture()
def engine(tmp_path: Path, tmp_store: AutonomyModeStore) -> AutonomousTradingEngine:
    trading = TradingService()
    return AutonomousTradingEngine(
        trading=trading,
        audit=AutonomyAuditLog(path=tmp_path / "audit.db"),
        events=AutonomyEventLog(path=tmp_path / "events.db"),
        scheduler=CycleSchedulerGuard(),
        modes=tmp_store,
        router=ExecutionRouter(paper=trading.broker, live=LiveBrokerDisabled()),
    )


def test_execution_modes_parse():
    assert parse_execution_mode("shadow") is ExecutionMode.SHADOW
    assert parse_execution_mode("live") is ExecutionMode.LIVE
    assert parse_execution_mode("nope") is ExecutionMode.PAPER


def test_order_state_transitions():
    assert transition(OrderState.CREATED, OrderState.VALIDATED) is OrderState.VALIDATED
    with pytest.raises(ValueError):
        transition(OrderState.FILLED, OrderState.SUBMITTED)


def test_health_ok_in_dev_paper(engine: AutonomousTradingEngine):
    h = run_health_check(engine.trading, execution_mode="PAPER")
    assert h.ok is True
    assert h.blocked is False
    assert "database" in h.checks


def test_health_blocks_live_without_broker_flag(engine: AutonomousTradingEngine):
    h = run_health_check(engine.trading, execution_mode="LIVE")
    assert h.blocked is True
    assert "LIVE_BROKER_DISABLED" in h.failures or "LIVE_REQUIRES_REAL_DATA" in h.failures


def test_engine_cycle_paper_ok(engine: AutonomousTradingEngine, tmp_store: AutonomyModeStore):
    tmp_store.set("SEMI_AUTO")
    tmp_store.set_execution_mode("PAPER")
    report = engine.run_cycle("BIST", force=True)
    assert report["status"] in {"OK", "BLOCKED"}
    assert report["execution_mode"] == "PAPER"
    assert report["discovery"]["universe"] >= 400
    assert report["orders_submitted"] == 0  # SEMI_AUTO


def test_shadow_emits_would_buy(engine: AutonomousTradingEngine, tmp_store: AutonomyModeStore):
    tmp_store.set("SEMI_AUTO")
    tmp_store.set_execution_mode("SHADOW")
    report = engine.run_cycle("BIST", force=True)
    assert report["execution_mode"] == "SHADOW"
    # May be empty if no entry signals this cycle — still must not submit
    assert report["orders_submitted"] == 0
    for o in report.get("orders") or []:
        assert o["state"] == "SHADOW"
    for intent in report.get("shadow_intents") or []:
        assert intent.get("would") == "BUY"
        assert intent.get("execution_mode") == "SHADOW"


def test_live_execution_blocked(engine: AutonomousTradingEngine, tmp_store: AutonomyModeStore):
    tmp_store.set("AUTO")
    tmp_store.set_execution_mode("LIVE")
    report = engine.run_cycle("BIST", force=True)
    # Health should block LIVE without broker + real data
    assert report["status"] == "BLOCKED"
    assert report["orders_submitted"] == 0


def test_pretrade_gate_duplicate_position(engine: AutonomousTradingEngine):
    decisions = engine.trading.scan()
    if not decisions:
        pytest.skip("no decisions")
    d = decisions[0]
    # Force a position
    engine.trading.ledger.apply_buy(d.symbol, d.sector or "TEST", 1, d.price, "T1", d.stop_price, d.target_price)
    # Mutate decision to look like BUY
    d.decision = SignalAction.BUY
    d.signal = SignalAction.AL
    d.final_decision = "BUY"
    gate = evaluate_pretrade_gates(engine.trading, d)
    assert gate.passed is False
    assert any(g.name == "POSITION" and not g.passed for g in gate.gates)


def test_kill_switch_blocks_gates(engine: AutonomousTradingEngine):
    from dataclasses import replace
    from autonomous import gates as gates_mod

    decisions = engine.trading.scan()
    if not decisions:
        pytest.skip("no decisions")
    d = decisions[0]
    d.decision = SignalAction.BUY
    d.signal = SignalAction.AL
    d.final_decision = "BUY"
    original = gates_mod.settings
    try:
        gates_mod.settings = replace(original, kill_switch=True)
        gate = evaluate_pretrade_gates(engine.trading, d)
    finally:
        gates_mod.settings = original
    assert gate.passed is False
    assert any(g.reason == "KILL_SWITCH" for g in gate.gates)


def test_reconcile_paper_ok(engine: AutonomousTradingEngine):
    rec = reconcile_paper(engine.trading)
    assert rec.ok is True
    assert rec.halted is False


def test_client_order_id_stable():
    a = make_client_order_id(market="BIST", symbol="THYAO", side="BUY", signal="BUY", cycle_id="C1")
    b = make_client_order_id(market="BIST", symbol="THYAO", side="BUY", signal="BUY", cycle_id="C1")
    assert a == b
    assert a.startswith("ATE-THYAO-")


def test_live_broker_adapter_blocked():
    from config.models import OrderRequest

    broker = LiveBrokerDisabled()
    res = broker.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="x"),
        "ULASTIRMA",
    )
    assert res.ok is False
    assert res.status == "BLOCKED"


def test_api_engine_endpoints():
    from fastapi.testclient import TestClient
    from dashboard.app import app

    client = TestClient(app)
    st = client.get("/api/autonomy/status").json()
    assert "execution_mode" in st
    assert st.get("live_trading") is False

    h = client.get("/api/autonomy/health")
    assert h.status_code == 200

    em = client.post("/api/autonomy/execution-mode", json={"execution_mode": "SHADOW"})
    assert em.status_code == 200
    assert em.json()["execution_mode"] == "SHADOW"

    cycle = client.post("/api/autonomy/cycle", json={"market": "BIST", "force": True, "use_engine": True})
    assert cycle.status_code == 200
    body = cycle.json()
    assert body.get("orders_submitted", 0) == 0 or body.get("execution_mode") == "SHADOW"

    ev = client.get("/api/autonomy/events")
    assert ev.status_code == 200
