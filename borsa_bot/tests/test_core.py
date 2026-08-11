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
