"""Desk gate for AUTO autonomy entries — offline / fail-closed."""

from __future__ import annotations

from types import SimpleNamespace

from autonomous.desk_gate import evaluate_desk_gate


class _FakeLedger:
    def daily_loss_pct(self) -> float:
        return 0.0

    def drawdown_pct(self) -> float:
        return 0.0


class _FakeTrading:
    def __init__(self) -> None:
        self.ledger = _FakeLedger()

    def paper_wallet(self) -> dict:
        return {"cash": 100_000, "equity": 100_000, "positions": [], "open_positions": 0, "max_open_positions": 5}

    @property
    def provider(self):
        raise RuntimeError("offline")


def test_desk_gate_blocks_negative_ev():
    trading = _FakeTrading()
    decision = SimpleNamespace(symbol="TEST")
    out = evaluate_desk_gate(
        trading,
        decision,
        {
            "symbol": "TEST",
            "final_decision": "BUY",
            "decision": "BUY",
            "scores": {"liquidity": 80},
            "opportunity": {"expected_value": -0.5, "risk_reward": 1.0},
            "data_source_kind": "DELAYED",
            "regime": "BULL",
            "price": 10.0,
            "spread_pct": 0.2,
        },
        require_buy=True,
    )
    assert out["allowed"] is False
    assert "DESK" in out["reason"] or out["veto"] or out["entry_action"] != "BUY"


def test_desk_gate_observe_does_not_require_buy():
    trading = _FakeTrading()
    decision = SimpleNamespace(symbol="TEST")
    out = evaluate_desk_gate(
        trading,
        decision,
        {
            "symbol": "TEST",
            "final_decision": "WAIT",
            "decision": "WAIT",
            "scores": {"liquidity": 70},
            "opportunity": {"expected_value": 0.8, "risk_reward": 2.0},
            "data_source_kind": "DELAYED",
            "regime": "BULL",
            "price": 10.0,
            "spread_pct": 0.2,
        },
        require_buy=False,
    )
    assert out["fail_closed"] is False
    assert "decision" in out


def test_engine_status_includes_desk_honesty(tmp_path):
    from autonomous.audit import AutonomyAuditLog
    from autonomous.engine import AutonomousTradingEngine
    from autonomous.events import AutonomyEventLog
    from autonomous.mode_store import AutonomyModeStore
    from autonomous.scheduler import CycleSchedulerGuard
    from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled
    from strategy.service import TradingService

    trading = TradingService()
    eng = AutonomousTradingEngine(
        trading=trading,
        audit=AutonomyAuditLog(path=tmp_path / "a.db"),
        events=AutonomyEventLog(path=tmp_path / "e.db"),
        scheduler=CycleSchedulerGuard(),
        modes=AutonomyModeStore(path=tmp_path / "m.json"),
        router=ExecutionRouter(paper=trading.broker, live=LiveBrokerDisabled()),
    )
    st = eng.status()
    assert st["desk_gate_auto"] is True
    assert st["honesty"]["full_level8_claimed"] is False
    assert st["honesty"]["live_ready"] is False
    assert st["live_trading"] is False


def test_halt_and_clear_api():
    from fastapi.testclient import TestClient

    from dashboard.app import app, engine

    client = TestClient(app)
    engine.clear_halt()
    r = client.post("/api/autonomy/halt", json={"reason": "TEST_HALT"})
    assert r.status_code == 200
    assert r.json()["halted"] is True
    st = client.get("/api/autonomy/status").json()
    assert st.get("halted") is True or st.get("blocked") is True
    r2 = client.post("/api/autonomy/clear-halt")
    assert r2.status_code == 200
    assert r2.json()["halted"] is False
