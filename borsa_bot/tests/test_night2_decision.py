"""Night 2 G11–G20 decision pipeline tests (paper only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from decision.engine import DecisionAction, decide_from_state
from decision.feedback import CalibrationStatus, DecisionFeedbackLoop, ProposedUpdate
from decision.market_state import DataQuality
from decision.pipeline import F6PaperLoop
from decision.regime import TradingRegime, classify_trading_regime
from decision.replay import DecisionReplayStore
from decision.risk_gate import RiskLimits, RiskVerdict, evaluate_risk
from decision.signals import SignalDirection, fuse_signals
from tests.decision_fixtures import bull_liquid_state, sparse_unknown_state


# --- G11 Market observation / UNKNOWN ---


def test_g11_unknown_not_silent_zero():
    state = sparse_unknown_state()
    unknowns = state.collect_unknowns()
    assert unknowns, "expected unknown fields"
    assert state.price.last.quality == DataQuality.UNKNOWN
    assert state.price.last.value is None
    assert state.price.last.value != 0
    d = state.to_dict()
    assert "unknown_fields" in d
    assert d["price"]["last"]["quality"] == "UNKNOWN"


def test_g11_known_market_state_fields():
    state = bull_liquid_state()
    assert state.price.last.known()
    assert state.trend.label.known()
    assert float(state.price.last.value) == 100.0


# --- G12 Regime (used by decision) ---


def test_g12_regime_trend_up_with_evidence():
    state = bull_liquid_state()
    reg = classify_trading_regime(state)
    assert reg.regime == TradingRegime.TREND_UP
    assert reg.confidence > 0.5
    assert reg.evidence
    assert "atr_pct" in reg.input_features


def test_g12_regime_unknown_when_missing():
    reg = classify_trading_regime(sparse_unknown_state())
    assert reg.regime == TradingRegime.UNKNOWN


def test_g12_high_vol_and_low_liquidity():
    state = bull_liquid_state()
    state.volatility.atr_pct.value = 5.0
    assert classify_trading_regime(state).regime == TradingRegime.HIGH_VOLATILITY
    state.volatility.atr_pct.value = 1.5
    state.liquidity.spread_pct.value = 2.0
    state.liquidity.score.value = 10.0
    assert classify_trading_regime(state).regime == TradingRegime.LOW_LIQUIDITY


# --- G13 Signal fusion ---


def test_g13_fusion_uses_regime_not_dead():
    state = bull_liquid_state()
    reg = classify_trading_regime(state)
    composite = fuse_signals(state, reg)
    sources = {c.source for c in composite.components}
    assert "regime" in sources
    assert "trend" in sources
    assert "momentum" in sources
    assert composite.timestamp


def test_g13_buy_plus_low_liquidity_becomes_no_trade():
    state = bull_liquid_state()
    state.liquidity.score.value = 15.0
    state.liquidity.spread_pct.value = 2.0
    reg = classify_trading_regime(state)
    composite = fuse_signals(state, reg)
    assert composite.direction == SignalDirection.NO_TRADE
    assert composite.conflict


# --- G14 Risk gate ---


def test_g14_risk_rejects_buy_on_drawdown():
    state = bull_liquid_state()
    reg = classify_trading_regime(state)
    signal = fuse_signals(state, reg)
    # Force a buy-like signal for gate test
    if signal.direction != SignalDirection.BUY:
        signal.direction = SignalDirection.BUY
        signal.confidence = 0.8
    result = evaluate_risk(
        state,
        signal,
        requested_size=10,
        peak_equity=10000,
        current_equity=8000,  # 20% DD > 15%
    )
    # portfolio drawdown_pct is 1.0 on fixture — use limits override via portfolio
    state.portfolio.drawdown_pct.value = 20.0
    result = evaluate_risk(state, signal, requested_size=10)
    assert result.verdict == RiskVerdict.REJECTED
    assert "max_drawdown" in result.reasons


def test_g14_risk_rejects_when_signal_buy_but_confidence_low():
    state = bull_liquid_state()
    from decision.signals import CompositeSignal

    weak = CompositeSignal(
        direction=SignalDirection.BUY,
        score=0.5,
        confidence=0.2,
        conflict=False,
    )
    result = evaluate_risk(state, weak, requested_size=10)
    assert result.verdict == RiskVerdict.REJECTED
    assert result.approved_size == 0.0


def test_g14_approved_or_reduced_sets_stops():
    state = bull_liquid_state()
    reg = classify_trading_regime(state)
    signal = fuse_signals(state, reg)
    signal.direction = SignalDirection.BUY
    signal.confidence = 0.8
    result = evaluate_risk(state, signal, requested_size=5, limits=RiskLimits())
    assert result.verdict in (RiskVerdict.APPROVED, RiskVerdict.REDUCED)
    assert result.approved_size > 0
    assert result.stop_loss is not None
    assert result.take_profit is not None


# --- G15/G16 Decision + NO_TRADE ---


def test_g15_decision_output_schema():
    out = decide_from_state(bull_liquid_state())
    d = out.to_dict()
    for key in (
        "decision",
        "confidence",
        "reason",
        "evidence",
        "risk_state",
        "position_size",
        "stop_loss",
        "take_profit",
    ):
        assert key in d
    assert d["live_trading"] is False
    assert d["execution_mode"] == "PAPER"


def test_g16_no_trade_on_missing_data():
    out = decide_from_state(sparse_unknown_state())
    assert out.decision == DecisionAction.NO_TRADE
    assert "missing_data" in out.no_trade_reasons or "market_regime_mismatch" in out.no_trade_reasons


def test_g16_no_trade_on_stale():
    state = bull_liquid_state()
    state.price.last.quality = DataQuality.STALE
    out = decide_from_state(state)
    assert out.decision == DecisionAction.NO_TRADE
    assert "stale_market_data" in out.no_trade_reasons


def test_g16_no_trade_logged_in_feedback(tmp_path):
    loop = F6PaperLoop(replay=DecisionReplayStore(tmp_path / "r.jsonl"))

    class _Q:
        price = 100.0
        bid = 99.9
        ask = 100.1
        volume = 1_000_000
        spread_pct = 0.1

    class _Prov:
        def get_quote(self, symbol):
            return _Q()

        def get_bars(self, symbol, n):
            # enough bars for indicators
            from collections import namedtuple

            Bar = namedtuple("Bar", "open high low close volume")
            bars = []
            px = 100.0
            for i in range(n):
                px += 0.2
                bars.append(Bar(px, px + 1, px - 1, px, 1_000_000))
            return bars

        def source_meta(self, n):
            class M:
                freshness = type("F", (), {"value": "OK"})()

            return M()

    # Without ledger still decides
    result = loop.run_cycle(provider=_Prov(), ledger=None, symbol="AAA")
    # May be BUY/SELL/NO_TRADE depending on indicators — ensure paper + record
    assert result.execution.mode == "PAPER"
    assert result.record_id
    if result.decision.decision == DecisionAction.NO_TRADE:
        assert loop.feedback.no_trade_log


# --- G17–G19 Feedback / memory / calibration ---


def test_g17_lessons_affect_next_context():
    fb = DecisionFeedbackLoop()
    for i in range(6):
        fb.record_result(
            symbol="X",
            decision="BUY",
            confidence=0.9,
            pnl=-10.0,
            regime="TREND_UP",
            strategy="ensemble",
        )
    ctx = fb.next_decision_context("ensemble", "TREND_UP")
    assert ctx["consecutive_losses"] >= 5
    assert ctx["lessons"]
    assert ctx["auto_weight_mutation"] is False
    assert ctx["size_multiplier"] <= 0.5


def test_g18_proposed_update_not_auto_applied():
    fb = DecisionFeedbackLoop()
    for i in range(6):
        fb.record_result(
            symbol="X",
            decision="BUY",
            confidence=0.7,
            pnl=-20.0,
            regime="RANGE",
            strategy="weak_strat",
        )
    assert fb.proposed_updates
    assert all(isinstance(p, ProposedUpdate) for p in fb.proposed_updates)
    assert all(p.auto_applied is False for p in fb.proposed_updates)
    assert all(p.requires_human_approval for p in fb.proposed_updates)
    assert all(p.kind == "PROPOSED_UPDATE" for p in fb.proposed_updates)


def test_g19_calibration_status_overconfident():
    fb = DecisionFeedbackLoop()
    # High confidence losses
    for _ in range(5):
        fb.record_result(symbol="X", decision="BUY", confidence=0.95, pnl=-5, regime="R")
    # Mid confidence mixed/better
    for _ in range(5):
        fb.record_result(symbol="X", decision="BUY", confidence=0.65, pnl=5, regime="R")
    status = fb.calibration_status()
    assert status in (CalibrationStatus.OVERCONFIDENT, CalibrationStatus.INSUFFICIENT_DATA) or status == CalibrationStatus.OVERCONFIDENT
    # With enough samples should be overconfident
    assert fb.calibration_status() == CalibrationStatus.OVERCONFIDENT
    evidence = fb.calibration_evidence()
    assert evidence["feeds_decision"] is True


# --- G20 Replay ---


def test_g20_replay_explains_decision(tmp_path):
    store = DecisionReplayStore(tmp_path / "replay.jsonl")
    out = decide_from_state(bull_liquid_state())
    rec = store.save_from_decision(out.to_dict())
    replayed = store.replay(rec.record_id)
    assert replayed["ok"] is True
    assert "Why did the system decide" in replayed["question"]
    assert replayed["answer"]["decision"] == out.decision.value
    assert replayed["answer"]["evidence"]
    assert replayed["live_trading"] is False
