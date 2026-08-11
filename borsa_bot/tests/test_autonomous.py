"""Phase 6 autonomy — discovery, filter, gates, paper-only, market isolation."""
from __future__ import annotations

from pathlib import Path

import pytest

from autonomous.agent import AutonomousAgent
from autonomous.audit import AutonomyAuditLog, make_idempotency_key
from autonomous.discovery import discover_bist, discover_crypto
from autonomous.explain import explain_decision
from autonomous.fast_filter import fast_filter_bist
from autonomous.mode_store import AutonomyModeStore
from autonomous.modes import UserTradingMode, auto_paper_allowed, parse_user_mode
from autonomous.scheduler import CycleSchedulerGuard
from config.settings import settings
from data.providers import create_provider
from strategy.service import TradingService


@pytest.fixture()
def tmp_audit(tmp_path: Path) -> AutonomyAuditLog:
    return AutonomyAuditLog(path=tmp_path / "autonomy_audit.db")


@pytest.fixture()
def tmp_mode(tmp_path: Path) -> AutonomyModeStore:
    return AutonomyModeStore(path=tmp_path / "autonomy_mode.json")


def test_parse_modes_and_live_alias_blocked(tmp_mode: AutonomyModeStore):
    assert parse_user_mode("semi") is UserTradingMode.SEMI_AUTO
    assert auto_paper_allowed(UserTradingMode.AUTO) is True
    assert auto_paper_allowed(UserTradingMode.PAPER) is False
    # Store refuses LIVE alias → PAPER
    assert tmp_mode.set("LIVE") is UserTradingMode.PAPER
    assert tmp_mode.set("AUTO") is UserTradingMode.AUTO


def test_discovery_bist100_marks_provider_md_only():
    provider = create_provider(settings.data_provider)
    discovered = discover_bist(provider_symbols=provider.list_symbols())
    assert len(discovered) >= 400  # tradeable catalog
    with_md = [d for d in discovered if d.has_market_data]
    # Simulated UNIVERSE is small — must not fabricate MD for all 100
    assert 0 < len(with_md) < 50
    assert any(not d.has_market_data for d in discovered)


def test_fast_filter_logs_universe_stats():
    provider = create_provider(settings.data_provider)
    discovered = discover_bist(provider_symbols=provider.list_symbols())
    filt = fast_filter_bist(discovered, provider, favorites={"THYAO"}, max_deep=40)
    assert filt.universe >= 400
    assert filt.with_market_data >= 1
    assert filt.fast_filter == len(filt.candidates)
    assert filt.fast_filter <= filt.with_market_data
    assert "THYAO" in filt.candidates or "THYAO" not in {d.symbol for d in discovered if d.has_market_data}


def test_explain_marks_confidence_not_probability():
    card = explain_decision(
        {
            "symbol": "THYAO",
            "final_decision": "BUY",
            "ai_confidence": 82,
            "regime": "BULL",
            "mtf": {"15m": "BULL", "1h": "BULL", "4h": "SIDE"},
            "data_source_kind": "SIMULATED",
            "ai_trade_plan": {"entry_zone": {"low": 1, "high": 2}, "stop_loss": 0.9, "target1": {"price": 3}, "risk_reward": 2.1},
        }
    )
    assert card["calibrated_probability"] is None
    assert card["heuristic"] is True
    assert card["ml_model"] is False
    assert "NOT calibrated" in card["confidence_label"]


def test_idempotency_key_stable_in_window():
    from datetime import datetime, timezone

    when = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    a = make_idempotency_key("BIST", "THYAO", "BUY", window_minutes=15, when=when)
    b = make_idempotency_key("BIST", "THYAO", "BUY", window_minutes=15, when=when)
    assert a == b
    assert "THYAO" in a


def test_scheduler_blocks_overlap():
    g = CycleSchedulerGuard()
    ok, _ = g.try_begin("BIST", min_interval_sec=60)
    assert ok
    ok2, reason = g.try_begin("BIST", min_interval_sec=60)
    assert not ok2
    assert "RUNNING" in reason or "COOLDOWN" in reason
    g.end("BIST")
    ok3, reason3 = g.try_begin("BIST", min_interval_sec=60)
    assert not ok3
    assert "COOLDOWN" in reason3
    ok4, _ = g.try_begin("BIST", min_interval_sec=60, force=True)
    assert ok4
    g.end("BIST")


def test_bist_cycle_paper_only_no_live(tmp_path: Path, tmp_audit: AutonomyAuditLog, tmp_mode: AutonomyModeStore):
    trading = TradingService()
    agent = AutonomousAgent(trading=trading, audit=tmp_audit, scheduler=CycleSchedulerGuard())
    agent.mode_store = tmp_mode
    tmp_mode.set("SEMI_AUTO")
    report = agent.run_bist_cycle(force=True)
    assert report["live_broker"] == "DISABLED"
    assert report["status"] in {"OK", "KILL_SWITCH_ACTIVE", "BLOCKED_LIVE_MODE"}
    assert report["paper_orders"] == 0  # SEMI_AUTO never auto-fills
    assert report["discovery"]["universe"] >= 400
    filt = report["filter_stats"]
    assert filt.get("UNIVERSE", 0) >= 400
    assert filt.get("DEEP_ANALYSIS", 0) <= filt.get("WITH_MARKET_DATA", 99) + 5


def test_paused_mode_skips(tmp_audit: AutonomyAuditLog, tmp_mode: AutonomyModeStore):
    agent = AutonomousAgent(trading=TradingService(), audit=tmp_audit, scheduler=CycleSchedulerGuard())
    agent.mode_store = tmp_mode
    tmp_mode.set("PAUSED")
    report = agent.run_bist_cycle(force=False)
    assert report["status"] == "PAUSED"
    assert report["paper_orders"] == 0


def test_crypto_disabled_isolated(tmp_audit: AutonomyAuditLog, tmp_mode: AutonomyModeStore):
    agent = AutonomousAgent(trading=TradingService(), audit=tmp_audit, scheduler=CycleSchedulerGuard())
    agent.mode_store = tmp_mode
    tmp_mode.set("PAPER")
    report = agent.run_crypto_cycle(force=True)
    # Default CRYPTO_ENABLED=false → skip without touching BIST
    assert report["status"] == "SKIPPED"
    assert report["live_broker"] == "DISABLED"
    # BIST still works after crypto skip
    bist = agent.run_bist_cycle(force=True)
    assert bist["market"] == "BIST"
    assert bist["status"] in {"OK", "KILL_SWITCH_ACTIVE", "BLOCKED_LIVE_MODE", "SKIPPED_DUPLICATE_SCAN"} or bist.get("live_broker") == "DISABLED"


def test_discover_crypto_empty_when_no_symbols():
    assert discover_crypto(provider_symbols=[]) == []


def test_duplicate_order_key_claim(tmp_audit: AutonomyAuditLog):
    key = make_idempotency_key("BIST", "THYAO", "BUY", window_minutes=15)
    assert tmp_audit.claim_order_key(key, "THYAO", "BUY") is True
    assert tmp_audit.claim_order_key(key, "THYAO", "BUY") is False


def test_scan_symbols_filter_does_not_break_default():
    svc = TradingService()
    all_d = svc.scan()
    one = svc.scan(symbols=["THYAO"])
    assert all(d.symbol == "THYAO" for d in one) or one == []
    # Default scan still returns multiple when provider has them
    if all_d:
        assert len(all_d) >= len(one)


def test_autonomy_api_routes():
    from fastapi.testclient import TestClient
    from dashboard.app import app

    client = TestClient(app)
    st = client.get("/api/autonomy/status")
    assert st.status_code == 200
    body = st.json()
    assert body["live_broker"] == "DISABLED"
    assert body["live_trading"] is False

    bad = client.post("/api/autonomy/mode", json={"mode": "LIVE"})
    assert bad.status_code == 400

    ok = client.post("/api/autonomy/mode", json={"mode": "PAPER"})
    assert ok.status_code == 200
    assert ok.json()["user_trading_mode"] == "PAPER"

    cycle = client.post("/api/autonomy/cycle", json={"market": "BIST", "force": True})
    assert cycle.status_code == 200
    payload = cycle.json()
    assert payload.get("live_broker") == "DISABLED"
    assert payload.get("status") in {
        "OK",
        "PAUSED",
        "KILL_SWITCH_ACTIVE",
        "BLOCKED_LIVE_MODE",
        "SKIPPED_DUPLICATE_SCAN",
        "MODE_BLOCKS_ANALYSIS",
        "ERROR",
    }
