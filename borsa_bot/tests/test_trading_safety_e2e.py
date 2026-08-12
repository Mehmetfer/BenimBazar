"""Adversarial + humanless E2E trading safety scenarios — deterministic, NO UNSAFE ORDER."""

from __future__ import annotations

from pathlib import Path

from config.models import OrderRequest
from config.settings import settings
from trading_safety.circuit_breaker import CircuitBreaker
from trading_safety.kill_switch import KillSwitch
from trading_safety.modes import TradingExecutionMode
from trading_safety.order_gate import evaluate_order_gate, paper_ready_context
from trading_safety.pipeline import SafeExecutionPipeline
from trading_safety.reconcile import reconcile_bot_vs_broker
from trading_safety.restart import recover_after_restart
from trading_safety.scorecard import score_trading_autonomy
from trading_safety.unknown_order import UnknownOrderRegistry


def _order(cid: str) -> OrderRequest:
    return OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100.0, reason="e2e", client_order_id=cid)


def test_e2e_normal_paper_trade(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("e2e-ok"), "X", ctx=paper_ready_context(), signal="AL", strategy_decision="BUY", risk_decision="APPROVE")
    assert res.ok is True
    assert res.mode == "PAPER"
    assert settings.live_broker_enabled is False


def test_e2e_provider_failure(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    ctx = paper_ready_context(provider_healthy=False, provider_kind="UNAVAILABLE", data_present=False)
    res = pipe.submit(_order("e2e-prov"), "X", ctx=ctx)
    assert res.ok is False


def test_e2e_broker_timeout_unknown(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("e2e-to"), "X", ctx=paper_ready_context(), simulate_broker_timeout=True)
    assert res.status == "UNKNOWN"
    # must not open another order on same symbol while unknown
    res2 = pipe.submit(_order("e2e-to2"), "X", ctx=paper_ready_context())
    assert res2.ok is False
    assert "UNKNOWN" in res2.gate_reason


def test_e2e_duplicate_request(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    assert pipe.submit(_order("e2e-dup"), "X", ctx=paper_ready_context()).ok
    assert pipe.submit(_order("e2e-dup"), "X", ctx=paper_ready_context()).status == "DUPLICATE"


def test_e2e_process_restart_no_duplicate(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    assert pipe.submit(_order("e2e-rs"), "X", ctx=paper_ready_context()).ok
    # New pipeline, same idempotency DB path
    pipe2 = SafeExecutionPipeline(db_dir=tmp_path, idem=pipe.idem)
    assert pipe2.submit(_order("e2e-rs"), "X", ctx=paper_ready_context()).status == "DUPLICATE"
    rec = recover_after_restart(
        load_state=lambda: {"positions": {}, "cash": 1000},
        query_broker_positions=lambda: {},
        unknown_registry=UnknownOrderRegistry(),
    )
    assert rec.may_resume is True


def test_e2e_risk_limit_breach(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("e2e-risk"), "X", ctx=paper_ready_context(daily_loss_ok=False))
    assert res.ok is False
    assert "RISK" in res.gate_reason or "DAILY" in res.gate_reason


def test_e2e_stale_market_data(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("e2e-stale"), "X", ctx=paper_ready_context(data_fresh=False))
    assert res.ok is False


def test_e2e_kill_switch(tmp_path: Path):
    kill = KillSwitch()
    kill.activate("risk-triggered", source="risk-triggered")
    pipe = SafeExecutionPipeline(db_dir=tmp_path, kill=kill)
    assert pipe.submit(_order("e2e-kill"), "X", ctx=paper_ready_context()).ok is False


def test_e2e_reconciliation_mismatch(tmp_path: Path):
    rec = reconcile_bot_vs_broker(bot_positions={"THYAO": 0}, broker_positions={"THYAO": 5})
    assert rec.blocks_trading
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("e2e-rec"), "X", ctx=paper_ready_context(reconciliation_ok=False))
    assert res.ok is False


def test_adversarial_invalid_price(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("adv-px"), "X", ctx=paper_ready_context(price_valid=False, price=-1))
    assert res.ok is False


def test_adversarial_market_closed_micro(tmp_path: Path):
    ctx = paper_ready_context(
        mode=TradingExecutionMode.MICRO_LIVE,
        provider_kind="LIVE",
        market_open=False,
        live_broker_enabled=True,
        live_confirmed=True,
    )
    d = evaluate_order_gate(ctx)
    assert d.allowed is False


def test_adversarial_malformed_provider_kind(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    res = pipe.submit(_order("adv-kind"), "X", ctx=paper_ready_context(provider_kind="REQUIRED"))
    assert res.ok is False


def test_adversarial_circuit_breaker_after_failures(tmp_path: Path):
    cb = CircuitBreaker(trip_threshold=1)
    cb.record_failure("PROVIDER")
    pipe = SafeExecutionPipeline(db_dir=tmp_path, breaker=cb)
    assert pipe.submit(_order("adv-cb"), "X", ctx=paper_ready_context()).ok is False


def test_trading_scorecard_live_money_not_verified():
    card = score_trading_autonomy(
        engineering_score=8.45,
        safety_gates_ok=True,
        fail_closed_ok=True,
        idempotency_ok=True,
        unknown_order_ok=True,
        reconciliation_ok=True,
        restart_recovery_ok=True,
        risk_controls_ok=True,
        kill_circuit_ok=True,
        observability_audit_ok=True,
        adversarial_e2e_ok=True,
        live_broker_locked=True,
        critical_findings=0,
        all_mandatory_pass=True,
    )
    assert card.trading_safety_score >= 9.0
    assert card.live_money_readiness == "NOT VERIFIED"
    assert card.full_level8_claimed is False
    assert card.engineering_autonomy_score == 8.45
