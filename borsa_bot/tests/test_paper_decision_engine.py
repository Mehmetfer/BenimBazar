"""Paper decision engine — feedback loop, risk gates, NO LIVE."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ai.calibration import CalibrationMonitor
from analytics.paper_feedback import PaperDecisionFeedback, StrategyStats
from analytics.post_trade import review_closed_trade
from config.models import (
    CapitalMode,
    MarketRegime,
    OpportunityMetrics,
    ScoreBundle,
    SignalAction,
    TradePlan,
)
from config.settings import settings
from indicators.engine import compute_indicators
from portfolio.ledger import PortfolioLedger
from profit.ev import decide_matrix, dynamic_size_multiplier
from profit.modes import select_capital_mode
from profit.protection import initial_protect, update_profit_protection
from risk.engine import RiskEngine
from data.providers import SimulatedProvider
from strategy.ranking import example_ranking_report
from strategy.service import TradingService
from backtest.runner import run_simple_backtest


def test_live_still_blocked():
    assert settings.is_live is False
    svc = TradingService()
    h = svc.health()
    assert h["live_ready"] is False
    assert h["mode"] == "PAPER"
    # LIVE adapter / broker remain gated
    from execution.paper import PaperBroker
    from config.models import OrderRequest

    broker = PaperBroker(svc.ledger)
    # Paper broker refuses LIVE via settings — mode stays PAPER in this suite
    assert settings.mode == "PAPER"


def test_calibration_monitor_records_and_haircuts():
    mon = CalibrationMonitor()
    assert mon.confidence_haircut == 0.0
    # Underperforming high-confidence bucket
    for _ in range(6):
        mon.record(85, False)
    for _ in range(6):
        mon.record(65, True)
    assert mon.confidence_haircut > 0
    assert mon.adjust(80) < 80


def test_post_trade_lessons_generated():
    rev = review_closed_trade(
        symbol="THYAO",
        pnl=-120,
        entry_reason="volume breakout",
        regime_at_entry="BULL",
        regime_at_exit="BEAR",
        stop_distance_pct=0.5,
    )
    assert rev.won is False
    assert any("loser" in x.lower() or "stop" in x.lower() for x in rev.lessons)
    assert any("regime" in x.lower() for x in rev.lessons)


def test_strategy_feedback_retires_losing_strategy():
    fb = PaperDecisionFeedback()
    for i in range(6):
        fb.on_closed_trade(
            symbol="X",
            pnl=-100,
            entry_reason="test",
            regime_at_entry="BULL",
            regime_at_exit="BULL",
            stop_distance_pct=2.0,
            confidence=80,
            strategy="broken_alpha",
        )
    assert fb.is_strategy_retired("broken_alpha")
    assert fb.size_multiplier_for("broken_alpha") == 0.0
    ranking = fb.ranking_report()
    assert ranking and ranking[0]["retired"] is True


def test_strategy_feedback_reduces_size_before_retire():
    fb = PaperDecisionFeedback()
    # 3 losses — not yet retired but underperform
    for _ in range(3):
        fb.on_closed_trade(
            symbol="Y",
            pnl=-50,
            entry_reason="t",
            regime_at_entry="NEUTRAL",
            regime_at_exit="NEUTRAL",
            stop_distance_pct=2.0,
            confidence=70,
            strategy="weak",
        )
    assert fb.is_strategy_retired("weak") is False
    assert fb.size_multiplier_for("weak") <= 0.5


def test_drift_forces_defensive_capital_mode():
    fb = PaperDecisionFeedback()
    for _ in range(10):
        fb.on_closed_trade(
            symbol="Z",
            pnl=-80,
            entry_reason="t",
            regime_at_entry="BULL",
            regime_at_exit="BULL",
            stop_distance_pct=2.0,
            confidence=75,
            strategy="drift_strat",
        )
    assert fb.should_force_defensive() is True
    tmp = Path(tempfile.mkdtemp()) / "def.db"
    led = PortfolioLedger(tmp)
    mode = select_capital_mode(
        led,
        regime=MarketRegime.BULL,
        atr_index_pct=1.0,
        liquidity_ok=True,
        force_defensive=True,
    )
    assert mode == CapitalMode.DEFENSIVE


def test_low_confidence_is_no_trade():
    scores = ScoreBundle(
        technical=85,
        fundamental=70,
        market=70,
        sector=70,
        momentum=70,
        volume=70,
        news=50,
        liquidity=70,
        risk=20,
        ai_confidence=40,  # below default 55
        final=85,
    )
    plan = TradePlan(entry=100, stop=97, target1=106, target2=108, target3=110, risk_reward=2.0)
    opp = OpportunityMetrics(
        p_win=0.7,
        expected_return_pct=6,
        expected_loss_pct=3,
        risk_reward=2.0,
        expected_value=2.0,
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=40,
    )
    d = decide_matrix(
        scores=scores,
        opp=opp,
        owned=False,
        sell_pressure=0,
        conflict=False,
        news_block=False,
        capital_mode=CapitalMode.NORMAL,
        regime=MarketRegime.BULL,
    )
    assert d == SignalAction.NO_TRADE


def test_strong_bear_is_no_trade():
    scores = ScoreBundle(
        technical=90,
        fundamental=80,
        market=40,
        sector=70,
        momentum=80,
        volume=80,
        news=50,
        liquidity=80,
        risk=20,
        ai_confidence=90,
        final=90,
    )
    opp = OpportunityMetrics(
        p_win=0.7,
        expected_return_pct=6,
        expected_loss_pct=3,
        risk_reward=2.0,
        expected_value=2.0,
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=90,
    )
    d = decide_matrix(
        scores=scores,
        opp=opp,
        owned=False,
        sell_pressure=0,
        conflict=False,
        news_block=False,
        capital_mode=CapitalMode.NORMAL,
        regime=MarketRegime.STRONG_BEAR,
    )
    assert d == SignalAction.NO_TRADE


def test_strategy_blocked_is_no_trade():
    scores = ScoreBundle(
        technical=90,
        fundamental=80,
        market=70,
        sector=70,
        momentum=80,
        volume=80,
        news=50,
        liquidity=80,
        risk=20,
        ai_confidence=90,
        final=90,
    )
    opp = OpportunityMetrics(
        p_win=0.7,
        expected_return_pct=6,
        expected_loss_pct=3,
        risk_reward=2.0,
        expected_value=2.0,
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=90,
    )
    d = decide_matrix(
        scores=scores,
        opp=opp,
        owned=False,
        sell_pressure=0,
        conflict=False,
        news_block=False,
        capital_mode=CapitalMode.NORMAL,
        regime=MarketRegime.BULL,
        strategy_blocked=True,
    )
    assert d == SignalAction.NO_TRADE


def test_max_drawdown_kill_and_position_limits():
    tmp = Path(tempfile.mkdtemp()) / "dd.db"
    led = PortfolioLedger(tmp)
    # Simulate deep drawdown via cash wipe + marks
    with led._connect() as conn:
        conn.execute("UPDATE account SET cash=?, starting_cash=? WHERE id=1", (50_000, 100_000))
    led.mark_prices = {}
    # equity ~50k → DD 50%
    assert led.drawdown_pct() >= settings.max_drawdown_pct
    eng = RiskEngine(led)
    eng.refresh_pause_state()
    assert eng.paused is True
    assert eng.pause_reason in {"max_drawdown", "weekly_loss_limit"}

    mode = select_capital_mode(
        led, regime=MarketRegime.BULL, atr_index_pct=1.0, liquidity_ok=True
    )
    assert mode == CapitalMode.KILL_SWITCH


def test_stop_loss_never_widens_and_risk_requires_stop():
    p = SimulatedProvider(seed=3)
    ind = compute_indicators(p.get_bars("THYAO", 220))
    assert ind is not None
    st = initial_protect(100, 96)
    st2, _ = update_profit_protection(
        entry=100,
        price=90,
        stop=96,
        ind=ind,
        t1=104,
        t2=108,
        t3=112,
        state=st,
        momentum_ok=False,
    )
    assert st2.stop >= 96

    tmp = Path(tempfile.mkdtemp()) / "stop.db"
    led = PortfolioLedger(tmp)
    eng = RiskEngine(led)
    plan = TradePlan(entry=100, stop=101, target1=105, target2=106, target3=108, risk_reward=1.5)
    rd = eng.evaluate_entry(
        symbol="THYAO",
        sector="ULASTIRMA",
        price=100,
        ind=ind,
        action=SignalAction.BUY,
        plan=plan,
    )
    assert rd.allowed is False
    assert rd.reason == "invalid_atr_stop"


def test_position_limit_rejects():
    tmp = Path(tempfile.mkdtemp()) / "lim.db"
    led = PortfolioLedger(tmp)
    p = SimulatedProvider(seed=4)
    ind = compute_indicators(p.get_bars("THYAO", 220))
    assert ind is not None
    # Fill max open positions
    for i, sym in enumerate(["THYAO", "GARAN", "SISE", "EREGL", "BIMAS"][: settings.max_open_positions]):
        led.apply_buy(sym, "SEC", 1, 10 + i, f"o{i}", stop=9, target=12)
    eng = RiskEngine(led)
    plan = TradePlan(entry=100, stop=97, target1=106, target2=108, target3=110, risk_reward=2.0)
    opp = OpportunityMetrics(
        p_win=0.7,
        expected_return_pct=6,
        expected_loss_pct=3,
        risk_reward=2.0,
        expected_value=2.0,
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=80,
    )
    rd = eng.evaluate_entry(
        symbol="AKBNK",
        sector="BANKA",
        price=100,
        ind=ind,
        action=SignalAction.BUY,
        plan=plan,
        opportunity=opp,
    )
    assert rd.allowed is False
    assert rd.reason == "max_open_positions"


def test_strong_bear_size_mult_zero():
    opp = OpportunityMetrics(
        p_win=0.7,
        expected_return_pct=6,
        expected_loss_pct=3,
        risk_reward=2.0,
        expected_value=2.0,
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=80,
    )
    assert dynamic_size_multiplier(opp, capital_mode=CapitalMode.NORMAL, regime=MarketRegime.STRONG_BEAR) == 0.0


def test_paper_service_wires_feedback_and_health():
    svc = TradingService()
    assert svc.calibration is svc.paper_feedback.calibration
    assert svc.multi.calibration is svc.calibration
    h = svc.health()
    assert h["live_ready"] is False
    assert h["mode"] == "PAPER"
    assert "paper_decision_feedback" in h
    assert h["paper_decision_feedback"]["note"]
    assert example_ranking_report()[0].get("dead_illustrative") is True
    assert "DEAD" in h.get("strategy_ranking_example_note", "")


def test_monitor_exits_records_feedback_on_stop():
    svc = TradingService()
    # Seed a paper position with stop above current? Use stop very high to force exit
    sym = "THYAO"
    quote = svc.provider.get_quote(sym)
    entry = quote.price
    # stop above price → immediate stop hit on next monitor (price <= stop)
    stop = entry * 1.5
    target = entry * 2.0
    svc.ledger.apply_buy(sym, quote.sector, 2, entry, "seed", stop=stop, target=target)
    svc._entry_meta[sym] = {
        "confidence": 82,
        "strategy": "seed_test",
        "regime": "BULL",
        "entry_reason": "unit",
        "stop_distance_pct": 2.0,
        "entry": entry,
        "stop": stop,
        "target": target,
    }
    svc._protect_state[sym] = initial_protect(entry, stop)
    outs = svc.monitor_exits()
    assert any(o.get("ok") for o in outs)
    assert svc.paper_feedback.strategies.get("seed_test")
    assert svc.paper_feedback.lessons


def test_backtest_still_runs_after_paper_feedback():
    m = run_simple_backtest("THYAO", steps=60)
    assert m is not None
    assert hasattr(m, "sharpe")


def test_strategy_stats_retire_rules():
    st = StrategyStats(name="x", trades=5, wins=1, total_pnl=-200, gross_win=20, gross_loss=220)
    assert st.retired is True
    st2 = StrategyStats(name="y", trades=2, wins=0, total_pnl=-10, gross_win=0, gross_loss=10)
    assert st2.retired is False
