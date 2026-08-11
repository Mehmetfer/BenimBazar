from dataclasses import replace
from pathlib import Path
import tempfile

from backtest.runner import assert_no_lookahead, run_simple_backtest
from config.models import MarketRegime, SignalAction
from config.settings import settings
from data.providers import SimulatedProvider
from indicators.engine import compute_indicators
from portfolio.ledger import PortfolioLedger
from risk.engine import RiskEngine
from strategy.regime import detect_regime
from strategy.service import TradingService
from strategy.signal_engine import decide_action


def test_indicators_produce_values():
    p = SimulatedProvider(seed=1)
    bars = p.get_bars("THYAO", 220)
    ind = compute_indicators(bars)
    assert ind is not None
    assert 0 <= ind.rsi14 <= 100
    assert ind.atr14 > 0


def test_regime_enum():
    p = SimulatedProvider(seed=2)
    regime = detect_regime(p)
    assert isinstance(regime, MarketRegime)


def test_signal_thresholds():
    action = decide_action(80, 10, False, MarketRegime.BULL)
    assert action == SignalAction.AL
    action2 = decide_action(80, 10, False, MarketRegime.STRONG_BEAR)
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


def test_trading_service_dashboard():
    svc = TradingService()
    dash = svc.dashboard()
    assert "universe" in dash
    assert "portfolio" in dash
    assert dash["health"]["mode"] == "PAPER"


def test_backtest_metrics():
    m = run_simple_backtest("GARAN", steps=40)
    assert m.trades >= 0
    assert isinstance(m.net_return, float)
    assert hasattr(m, "sharpe")
    assert hasattr(m, "sortino")
    assert hasattr(m, "cagr")


def test_lookahead_guard():
    assert assert_no_lookahead([1, 2, 3], [1, 2, 3]) is True
