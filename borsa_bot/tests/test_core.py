from dataclasses import replace
from pathlib import Path
import tempfile

from backtest.runner import assert_no_lookahead, run_simple_backtest
from config.models import MarketRegime, SignalAction
from config.settings import settings
from data.providers import SimulatedProvider
from execution.paper import PaperBroker
from execution.safety import SafetyGate
from indicators.engine import compute_indicators
from portfolio.ledger import PortfolioLedger
from risk.engine import RiskEngine
from market_regime.engine import detect_regime
from strategy.service import TradingService
from signals.engine import decide_action, build_trade_plan
from config.models import OrderRequest


def test_indicators_produce_values():
    p = SimulatedProvider(seed=1)
    bars = p.get_bars("THYAO", 220)
    ind = compute_indicators(bars)
    assert ind is not None
    assert 0 <= ind.rsi14 <= 100
    assert ind.atr14 > 0
    assert ind.ema100 > 0
    assert ind.mfi14 >= 0
    assert ind.structure in {"HH_HL", "LH_LL", "RANGE"}


def test_regime_enum():
    p = SimulatedProvider(seed=2)
    regime = detect_regime(p)
    assert isinstance(regime, MarketRegime)


def test_signal_thresholds():
    action = decide_action(85, 10, False, MarketRegime.BULL)
    assert action == SignalAction.AL
    action2 = decide_action(85, 10, False, MarketRegime.STRONG_BEAR)
    assert action2 == SignalAction.BEKLE
    action3 = decide_action(40, 10, False, MarketRegime.BULL)
    assert action3 == SignalAction.ALMA


def test_risk_blocks_when_kill_switch():
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    led = PortfolioLedger(tmp)
    cfg = replace(settings, kill_switch=True)
    eng = RiskEngine(led, cfg)
    p = SimulatedProvider(seed=3)
    ind = compute_indicators(p.get_bars("THYAO", 220))
    assert ind is not None
    rd = eng.evaluate_entry(symbol="THYAO", sector="ULASTIRMA", price=100, ind=ind, action=SignalAction.AL)
    assert rd.allowed is False
    assert rd.reason == "KILL_SWITCH"


def test_risk_blocks_bad_rr():
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    led = PortfolioLedger(tmp)
    eng = RiskEngine(led)
    p = SimulatedProvider(seed=4)
    ind = compute_indicators(p.get_bars("GARAN", 220))
    assert ind is not None
    # Force tiny target via plan with rr < min
    from config.models import TradePlan
    plan = TradePlan(entry=100, stop=99, target1=100.5, target2=101, target3=102, risk_reward=0.5)
    rd = eng.evaluate_entry(symbol="GARAN", sector="BANKA", price=100, ind=ind, action=SignalAction.AL, plan=plan)
    assert rd.allowed is False
    assert rd.reason == "rr_below_minimum"


def test_duplicate_order_protection():
    tmp = Path(tempfile.mkdtemp()) / "dup.db"
    led = PortfolioLedger(tmp)
    broker = PaperBroker(led)
    order = OrderRequest(symbol="THYAO", side="BUY", quantity=1, price=10, reason="t", client_order_id="same")
    r1 = broker.submit(order, "ULASTIRMA")
    r2 = broker.submit(order, "ULASTIRMA")
    assert r1.ok is True
    assert r2.ok is False
    assert r2.status == "DUPLICATE"


def test_safety_stale_and_spread():
    gate = SafetyGate()
    ok, reason = gate.evaluate(
        data_fresh=False, api_ok=True, order_status_ok=True,
        spread_pct=0.1, daily_loss_pct=0, clock_ok=True,
    )
    assert ok is False and reason == "STALE_DATA"
    ok2, reason2 = gate.evaluate(
        data_fresh=True, api_ok=True, order_status_ok=True,
        spread_pct=5.0, daily_loss_pct=0, clock_ok=True, max_spread_pct=0.8,
    )
    assert ok2 is False and reason2 == "ABNORMAL_SPREAD"


def test_trade_plan_rr_floor():
    p = SimulatedProvider(seed=5)
    ind = compute_indicators(p.get_bars("ASELS", 220))
    assert ind is not None
    plan = build_trade_plan(p.get_quote("ASELS").price, ind)
    assert plan is None or plan.risk_reward >= settings.min_risk_reward


def test_trading_service_dashboard():
    svc = TradingService()
    dash = svc.dashboard()
    assert "universe" in dash
    assert "portfolio" in dash
    assert dash["health"]["mode"] == "PAPER"
    u0 = dash["universe"][0]
    assert "scores" in u0
    assert "reasons" in u0


def test_manual_approval_required():
    svc = TradingService()
    # Without approved flag should not silently fill when approval required
    res = svc.execute_signal("THYAO", approved=False)
    assert res["ok"] is False


def test_backtest_metrics():
    m = run_simple_backtest("GARAN", steps=40)
    assert m.trades >= 0
    assert hasattr(m, "sharpe")
    assert hasattr(m, "calmar")
    assert hasattr(m, "consecutive_losses_max")


def test_lookahead_guard():
    assert assert_no_lookahead([1, 2, 3], [1, 2, 3]) is True


def test_negative_ev_rejected():
    from config.models import OpportunityMetrics, TradePlan
    tmp = Path(tempfile.mkdtemp()) / "ev.db"
    led = PortfolioLedger(tmp)
    eng = RiskEngine(led)
    p = SimulatedProvider(seed=8)
    ind = compute_indicators(p.get_bars("THYAO", 220))
    assert ind is not None
    plan = TradePlan(entry=100, stop=98, target1=103, target2=104, target3=106, risk_reward=1.5)
    opp = OpportunityMetrics(
        p_win=0.3, expected_return_pct=3, expected_loss_pct=2, risk_reward=1.5,
        expected_value=-0.5, volatility_pct=2.0, drawdown_impact=0.5, position_size_mult=1.0, confidence=50,
    )
    rd = eng.evaluate_entry(
        symbol="THYAO", sector="ULASTIRMA", price=100, ind=ind, action=SignalAction.BUY,
        plan=plan, opportunity=opp,
    )
    assert rd.allowed is False
    assert rd.reason == "negative_or_zero_ev"


def test_no_add_to_losing_position():
    from profit.protection import refuse_add_to_loser, update_profit_protection, initial_protect
    assert refuse_add_to_loser(avg_cost=100, price=95) is True
    assert refuse_add_to_loser(avg_cost=100, price=105) is False
    p = SimulatedProvider(seed=9)
    ind = compute_indicators(p.get_bars("GARAN", 220))
    assert ind is not None
    st = initial_protect(100, 96)
    st2, _ = update_profit_protection(
        entry=100, price=90, stop=96, ind=ind, t1=104, t2=108, t3=112, state=st, momentum_ok=False,
    )
    assert st2.stop >= 96  # never widen


def test_risk_adjusted_ranking_prefers_lower_dd():
    from strategy.ranking import StrategyPerf, rank_strategies, example_ranking_report
    ranked = rank_strategies([
        StrategyPerf("A", 80, 45, 0.8, 1.0, 1.8, 1.4, 120),
        StrategyPerf("B", 45, 12, 1.4, 1.8, 3.7, 1.7, 90),
        StrategyPerf("C", 38, 8, 1.6, 2.1, 4.7, 1.9, 70),
    ])
    assert ranked[0].name == "C"
    assert example_ranking_report()[0]["name"] == "C_conservative"


def test_capital_mode_strong_bear():
    from profit.modes import select_capital_mode
    from config.models import CapitalMode, MarketRegime
    tmp = Path(tempfile.mkdtemp()) / "cm.db"
    led = PortfolioLedger(tmp)
    mode = select_capital_mode(led, regime=MarketRegime.STRONG_BEAR, atr_index_pct=2.0, liquidity_ok=True)
    assert mode == CapitalMode.CAPITAL_PROTECTION


def test_dashboard_exposes_opportunity():
    svc = TradingService()
    dash = svc.dashboard()
    assert dash["health"]["capital_mode"]
    assert "opportunity" in dash["universe"][0] or dash["universe"][0]["decision"]
