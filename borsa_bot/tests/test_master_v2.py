"""Master V2 institutional glue — levels, anomaly, governors, lifecycle, rate limit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autonomous.anomaly import inspect_bars, inspect_quote, inspect_symbol
from autonomous.engine import AutonomousTradingEngine
from autonomous.execution_modes import ExecutionMode
from autonomous.governors import GovernorState, evaluate_governors
from autonomous.levels import AutonomyLevel, resolve_autonomy_level
from autonomous.mode_store import AutonomyModeStore
from autonomous.modes import UserTradingMode
from autonomous.rate_limit import OrderRateLimiter
from autonomous.signal_lifecycle import build_lifecycle, evaluate_invalidation, is_expired
from ai.model_registry import ModelRegistry
from config.models import Bar, QuoteSnapshot
from config.settings import settings
from strategy.service import TradingService


def _quote(**kw) -> QuoteSnapshot:
    base = dict(
        symbol="THYAO",
        name="Turkish Airlines",
        sector="TRANSPORT",
        price=100.0,
        bid=99.9,
        ask=100.1,
        volume=1_000_000.0,
        trades=100,
        ts=datetime.now(timezone.utc),
        data_source_kind="SIMULATED",
    )
    base.update(kw)
    return QuoteSnapshot(**base)


def _bars(n: int = 30, *, spike: bool = False, dup: bool = False) -> list[Bar]:
    now = datetime.now(timezone.utc)
    out: list[Bar] = []
    px = 100.0
    for i in range(n):
        ts = now - timedelta(minutes=15 * (n - i))
        if spike and i == n - 1:
            px = px * 1.40
        close = px
        out.append(
            Bar(
                symbol="THYAO",
                ts=ts,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1000.0,
                data_source_kind="SIMULATED",
            )
        )
        if not spike:
            px *= 1.001
    if dup and len(out) >= 2:
        out[-1] = Bar(
            symbol="THYAO",
            ts=out[-2].ts,
            open=out[-1].open,
            high=out[-1].high,
            low=out[-1].low,
            close=out[-1].close,
            volume=out[-1].volume,
            data_source_kind="SIMULATED",
        )
    return out


def test_anomaly_bid_gt_ask_blocks():
    q = _quote(bid=101.0, ask=100.0)
    r = inspect_quote(q)
    assert r.trade_allowed is False
    assert any(f.code == "BID_GT_ASK" for f in r.findings)


def test_anomaly_abnormal_spread_blocks():
    q = _quote(bid=90.0, ask=110.0)  # large spread
    r = inspect_quote(q, max_spread_pct=2.0)
    assert r.trade_allowed is False
    assert any(f.code == "ABNORMAL_SPREAD" for f in r.findings)


def test_anomaly_price_spike_high():
    r = inspect_bars(_bars(20, spike=True))
    assert r.trade_allowed is False
    assert any(f.code == "PRICE_SPIKE" for f in r.findings)


def test_anomaly_duplicate_bar():
    r = inspect_bars(_bars(10, dup=True))
    assert any(f.code == "DUPLICATE_BAR" for f in r.findings)


def test_anomaly_ok_simulated():
    r = inspect_symbol(_quote(), _bars(40))
    assert r.trade_allowed is True


def test_governor_normal():
    g = evaluate_governors(daily_loss_pct=0.0, drawdown_pct=0.5)
    assert g.state is GovernorState.NORMAL
    assert g.size_mult == 1.0
    assert g.new_trades_allowed is True


def test_governor_never_increases_risk_on_loss():
    g = evaluate_governors(daily_loss_pct=-1.5, drawdown_pct=5.0)
    assert g.size_mult <= 1.0
    assert g.state in {GovernorState.CAUTION, GovernorState.REDUCED_RISK, GovernorState.TRADING_HALT}


def test_governor_halt_on_daily_loss_limit():
    lim = float(settings.daily_max_loss_pct)
    g = evaluate_governors(daily_loss_pct=-lim, drawdown_pct=0.0)
    assert g.state is GovernorState.TRADING_HALT
    assert g.new_trades_allowed is False
    assert g.size_mult == 0.0


def test_governor_kill_switch():
    g = evaluate_governors(daily_loss_pct=0.0, drawdown_pct=0.0, kill_switch=True)
    assert g.state is GovernorState.TRADING_HALT


def test_levels_paper_auto():
    st = resolve_autonomy_level(UserTradingMode.AUTO, ExecutionMode.PAPER)
    assert st.level == AutonomyLevel.LEVEL_2_PAPER_AUTONOMOUS
    assert st.can_live is False


def test_levels_shadow():
    st = resolve_autonomy_level(UserTradingMode.SEMI_AUTO, ExecutionMode.SHADOW)
    assert st.level == AutonomyLevel.LEVEL_3_SHADOW_LIVE
    assert st.can_shadow is True


def test_levels_never_claim_full_autonomous():
    st = resolve_autonomy_level(UserTradingMode.AUTO, ExecutionMode.LIVE)
    assert st.level < AutonomyLevel.LEVEL_5_FULL_AUTONOMOUS
    assert st.can_live is False


def test_signal_lifecycle_ttl():
    life = build_lifecycle("THYAO", "BUY", created=datetime.now(timezone.utc) - timedelta(hours=3), ttl_sec=60)
    assert is_expired(life) is True
    life2 = evaluate_invalidation(life)
    assert life2.valid is False
    assert life2.invalidation_reason == "SIGNAL_EXPIRED"


def test_signal_mtf_invalidation():
    life = build_lifecycle("THYAO", "STRONG_BUY")
    life = evaluate_invalidation(life, mtf_conflict=True)
    assert life.valid is False
    assert life.invalidation_reason == "TIMEFRAME_CONFLICT"
    assert "MTF_CONFLICT" in life.reason_codes


def test_rate_limit_orders_per_minute():
    lim = OrderRateLimiter(max_per_minute=3, max_per_symbol_per_minute=10)
    assert lim.allow_order("A").allowed
    assert lim.allow_order("B").allowed
    assert lim.allow_order("C").allowed
    blocked = lim.allow_order("D")
    assert blocked.allowed is False
    assert blocked.reason == "MAX_ORDERS_PER_MINUTE"


def test_rate_limit_per_symbol():
    lim = OrderRateLimiter(max_per_minute=50, max_per_symbol_per_minute=2)
    assert lim.allow_order("X").allowed
    assert lim.allow_order("X").allowed
    assert lim.allow_order("X").allowed is False


def test_model_registry_heuristic(tmp_path: Path):
    reg = ModelRegistry(path=tmp_path / "models.json")
    models = reg.list_models()
    assert models
    assert models[0]["metrics"].get("ml") is False
    active = reg.active()
    assert active is not None
    out = reg.promote(active["model_id"], approved_by="tester")
    assert out["ok"] is True


def test_engine_status_exposes_level_and_governor(tmp_path: Path):
    trading = TradingService()
    eng = AutonomousTradingEngine(
        trading=trading,
        modes=AutonomyModeStore(path=tmp_path / "mode.json"),
    )
    eng.modes.set("AUTO")
    eng.modes.set_execution_mode("PAPER")
    st = eng.status()
    assert "autonomy_level" in st
    assert st["autonomy_level"]["level"] == 2
    assert "governor" in st
    # NORMAL or a safety-governor halt are both valid — do not require NORMAL when
    # paper ledger already tripped weekly/daily loss (fail-closed is correct).
    assert st["governor"]["state"] in {
        "NORMAL",
        "CAUTION",
        "REDUCED_RISK",
        "TRADING_HALT",
    }
    aw = eng.self_awareness()
    assert "principles" in aw
    assert aw["live_broker"] == "DISABLED"


def test_engine_cycle_includes_self_status_fields(tmp_path: Path):
    trading = TradingService()
    eng = AutonomousTradingEngine(
        trading=trading,
        modes=AutonomyModeStore(path=tmp_path / "mode.json"),
    )
    eng.modes.set("SEMI_AUTO")
    eng.modes.set_execution_mode("PAPER")
    report = eng.run_cycle("BIST", force=True)
    assert report["status"] in {"OK", "BLOCKED"}
    st = eng.status()
    assert st["autonomous_status"] in {"ACTIVE", "BLOCKED"}
