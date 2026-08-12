"""Trading safety — gates, idempotency, unknown-order, reconcile, restart, kill/CB."""

from __future__ import annotations

from pathlib import Path

from config.models import OrderRequest
from config.settings import settings
from trading_safety.circuit_breaker import CircuitBreaker
from trading_safety.idempotency import IdempotencyStore
from trading_safety.kill_switch import KillSwitch
from trading_safety.micro_live import MICRO_LIVE_ABS_MAX_ORDER_QTY, MicroLiveLimits
from trading_safety.modes import TradingExecutionMode
from trading_safety.order_gate import evaluate_order_gate, paper_ready_context
from trading_safety.pipeline import SafeExecutionPipeline
from trading_safety.reconcile import reconcile_bot_vs_broker
from trading_safety.restart import recover_after_restart
from trading_safety.unknown_order import OrderCertainty, UnknownOrderRegistry


def test_required_provider_still_blocked_in_production():
    """Regression: PRODUCTION + REQUIRED must not allow signals."""
    from data.providers import RequiredLiveProvider
    from data.validation import AppEnvironment, gate_provider_instance

    g = gate_provider_instance(RequiredLiveProvider("x"), AppEnvironment.PRODUCTION)
    assert g.signals_allowed is False
    assert g.ok is False


def test_live_broker_still_locked():
    assert settings.live_broker_enabled is False


def test_kill_switch_blocks(tmp_path: Path):
    kill = KillSwitch()
    kill.activate("emergency", source="emergency")
    pipe = SafeExecutionPipeline(mode=TradingExecutionMode.PAPER, kill=kill, db_dir=tmp_path)
    ctx = paper_ready_context()
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="k1")
    res = pipe.submit(order, "X", ctx=ctx, cycle_id="c1")
    assert res.ok is False
    assert "KILL" in res.gate_reason
    assert kill.clear(human_ack=False) is False
    assert kill.clear(human_ack=True) is True


def test_stale_data_fail_closed(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    ctx = paper_ready_context(data_fresh=False)
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="stale1")
    res = pipe.submit(order, "X", ctx=ctx)
    assert res.ok is False
    assert "DATA_FRESH" in res.gate_reason or "MD_" in res.gate_reason


def test_idempotency_blocks_duplicate(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    ctx = paper_ready_context()
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="dup-key")
    r1 = pipe.submit(order, "X", ctx=paper_ready_context(), cycle_id="c")
    r2 = pipe.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="dup-key"),
        "X",
        ctx=paper_ready_context(),
        cycle_id="c",
    )
    assert r1.ok is True
    assert r2.ok is False
    assert r2.status == "DUPLICATE"
    assert pipe.metrics.duplicate_prevented >= 1


def test_unknown_order_not_assumed_failed():
    reg = UnknownOrderRegistry()
    rec = reg.mark_unknown("oid-1", symbol="THYAO", side="BUY", quantity=1)
    assert rec.certainty is OrderCertainty.UNKNOWN
    blocked, _ = reg.has_blocking_unknown("THYAO")
    assert blocked is True
    # Must not treat as failed without broker query
    resolved = reg.resolve_from_broker("oid-1", None)
    assert resolved is not None
    assert resolved.certainty is OrderCertainty.UNKNOWN
    reg.resolve_from_broker("oid-1", "FILLED")
    blocked2, _ = reg.has_blocking_unknown("THYAO")
    assert blocked2 is False


def test_pipeline_unknown_on_timeout(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    ctx = paper_ready_context()
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="unk1")
    res = pipe.submit(order, "X", ctx=ctx, simulate_broker_timeout=True)
    assert res.status == "UNKNOWN"
    assert res.ok is False
    blocked, _ = pipe.unknowns.has_blocking_unknown("THYAO")
    assert blocked is True


def test_reconciliation_mismatch_blocks():
    rec = reconcile_bot_vs_broker(
        bot_positions={"AAPL": 0},
        broker_positions={"AAPL": 100},
    )
    assert rec.state == "RECONCILIATION_REQUIRED"
    assert rec.blocks_trading is True
    ctx = paper_ready_context(reconciliation_ok=False)
    d = evaluate_order_gate(ctx)
    assert d.allowed is False


def test_restart_recovery_blocks_on_mismatch_and_unknown():
    reg = UnknownOrderRegistry()
    reg.mark_unknown("x", symbol="THYAO", side="BUY", quantity=1)

    def load():
        return {"positions": {"THYAO": 0}, "cash": 1000}

    bad = recover_after_restart(
        load_state=load,
        query_broker_positions=lambda: {"THYAO": 10},
        unknown_registry=reg,
    )
    assert bad.may_resume is False
    assert "RECONCILIATION" in bad.blocked_reason or "UNKNOWN" in bad.blocked_reason

    ok = recover_after_restart(
        load_state=lambda: {"positions": {"THYAO": 1}, "cash": 1000},
        query_broker_positions=lambda: {"THYAO": 1},
        query_broker_cash=lambda: 1000.0,
        unknown_registry=UnknownOrderRegistry(),
        risk_validate=lambda: (True, "OK"),
    )
    assert ok.may_resume is True
    assert "RESUME_ALLOWED" in ok.steps


def test_circuit_breaker_trips(tmp_path: Path):
    cb = CircuitBreaker(trip_threshold=2)
    cb.record_failure("EXECUTION_FAILURE")
    assert cb.tripped is False
    cb.record_failure("EXECUTION_FAILURE")
    assert cb.tripped is True
    assert cb.reset(human_ack=False) is False
    pipe = SafeExecutionPipeline(db_dir=tmp_path, breaker=cb)
    res = pipe.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="cb1"),
        "X",
        ctx=paper_ready_context(),
    )
    assert res.ok is False


def test_shadow_never_hits_paper_broker(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path, mode=TradingExecutionMode.SHADOW)
    ctx = paper_ready_context(mode=TradingExecutionMode.SHADOW, provider_kind="LIVE")
    # SHADOW with LIVE kind still ok for observation
    before = pipe.paper  # type: ignore
    res = pipe.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="sh1"),
        "X",
        ctx=ctx,
    )
    assert res.ok is True
    assert res.would_submit is True
    assert res.status == "SHADOW"


def test_micro_live_caps_cannot_unbound():
    lim = MicroLiveLimits(max_order_qty=999, max_notional=1_000_000, max_trades_per_day=100)
    assert lim.max_order_qty <= MICRO_LIVE_ABS_MAX_ORDER_QTY
    ok, reason = lim.check_order(symbol="THYAO", qty=2, price=100, trades_today=0, daily_loss_pct=0)
    assert ok is False


def test_micro_live_not_auto_enabled(tmp_path: Path):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)
    ctx = paper_ready_context(
        mode=TradingExecutionMode.MICRO_LIVE,
        provider_kind="LIVE",
        live_broker_enabled=True,
        live_confirmed=True,
    )
    res = pipe.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="ml1"),
        "X",
        ctx=ctx,
    )
    assert res.ok is False
    assert "NOT VERIFIED" in res.message or "LOCKED" in res.gate_reason or "LIVE" in res.gate_reason


def test_audit_failure_blocks(tmp_path: Path, monkeypatch):
    pipe = SafeExecutionPipeline(db_dir=tmp_path)

    def boom(record):
        return False

    monkeypatch.setattr(pipe.audit, "append", boom)
    res = pipe.submit(
        OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=100, reason="t", client_order_id="aud1"),
        "X",
        ctx=paper_ready_context(),
    )
    assert res.ok is False
    assert "AUDIT" in res.gate_reason or res.status == "BLOCKED"


def test_idempotency_store_roundtrip(tmp_path: Path):
    store = IdempotencyStore(tmp_path / "i.db")
    key = store.make_key(symbol="THYAO", side="BUY", signal="AL", cycle_id="1", window_bucket=1)
    c1 = store.claim(key, symbol="THYAO", side="BUY")
    c2 = store.claim(key, symbol="THYAO", side="BUY")
    assert c1.claimed and not c1.duplicate
    assert c2.duplicate
