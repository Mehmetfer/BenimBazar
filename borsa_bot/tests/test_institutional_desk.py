"""Institutional desk — committee, consensus, pipeline, position monitor."""

from __future__ import annotations

from dataclasses import replace

import pytest

from config.settings import settings
from desk.committee import MasterTradingCommittee
from desk.consensus import compute_consensus
from desk.entry import evaluate_entry
from desk.models import AnalystVote, StageStatus
from desk.pipeline import FinalDecisionPipeline
from desk.session import DeskSessionMode, current_session_mode
from profit.protection import initial_protect, update_profit_protection


def _sample_row(**kw) -> dict:
    base = {
        "symbol": "THYAO",
        "price": 100.0,
        "bid": 99.9,
        "ask": 100.1,
        "spread_pct": 0.2,
        "final_decision": "BUY",
        "decision": "BUY",
        "regime": "BULL",
        "scores": {"liquidity": 75, "technical": 72},
        "opportunity": {
            "expected_value": 0.8,
            "risk_reward": 2.5,
            "expected_return_pct": 2.0,
            "expected_loss_pct": 1.0,
        },
        "mtf": {"h1": "BULL", "h4": "BULL"},
        "conflict": False,
        "strategy_votes": {"momentum": "BUY"},
        "data_source_kind": "SIMULATED",
    }
    base.update(kw)
    return base


def test_consensus_risk_manager_veto():
    votes = [
        AnalystVote("quant_analyst", "BUY", 0.9, "strong edge"),
        AnalystVote("technical_analyst", "BUY", 0.85, "trend"),
        AnalystVote("risk_manager", "VETO", 0.95, "daily loss limit", risk="TRADING_HALT"),
    ]
    c = compute_consensus(votes, regime="BULL")
    assert c.veto is True
    assert c.decision == "NO_TRADE"


def test_consensus_model_disagreement():
    votes = [
        AnalystVote("quant_analyst", "BUY", 0.85, "edge"),
        AnalystVote("regime_analyst", "SELL", 0.74, "bear"),
        AnalystVote("technical_analyst", "NO_TRADE", 0.6, "neutral"),
        AnalystVote("market_analyst", "NO_TRADE", 0.55, "weak"),
        AnalystVote("risk_manager", "APPROVE", 0.7, "ok"),
    ]
    c = compute_consensus(votes, regime="BULL", disagreement_threshold=0.35)
    assert c.decision == "NO_TRADE"
    assert c.disagreement >= 0.35


def test_consensus_weighted_buy_not_majority():
    """Weighted quant+risk should win over more NO_TRADE votes with low weight."""
    votes = [
        AnalystVote("quant_analyst", "BUY", 0.88, "edge", expected_edge=0.5),
        AnalystVote("market_analyst", "NO_TRADE", 0.4, "weak"),
        AnalystVote("fundamental_analyst", "NO_TRADE", 0.0, "unavailable", data_quality="UNAVAILABLE"),
        AnalystVote("risk_manager", "APPROVE", 0.8, "ok"),
        AnalystVote("portfolio_manager", "APPROVE", 0.75, "room"),
        AnalystVote("execution_manager", "GO", 0.7, "liquid"),
        AnalystVote("technical_analyst", "BUY", 0.8, "trend"),
        AnalystVote("regime_analyst", "BUY", 0.7, "bull"),
    ]
    c = compute_consensus(votes, regime="BULL")
    assert c.decision == "BUY"
    assert not c.veto


def test_entry_wait_on_poor_execution():
    plan = evaluate_entry(
        price=100.0,
        bid=95.0,
        ask=105.0,
        spread_pct=2.0,
        liquidity_score=30.0,
        signal_decision="BUY",
        consensus_decision="BUY",
    )
    assert plan.action == "WAIT"
    assert plan.order_type == "PASSIVE_LIMIT"


def test_entry_no_market_on_low_liquidity():
    plan = evaluate_entry(
        price=100.0,
        bid=98.0,
        ask=102.0,
        spread_pct=1.8,
        liquidity_score=25.0,
        signal_decision="BUY",
        consensus_decision="BUY",
    )
    assert plan.action == "WAIT"
    assert plan.order_type != "MARKET"


def test_pipeline_fails_on_negative_ev():
    pipe = FinalDecisionPipeline()
    row = _sample_row(opportunity={"expected_value": -0.2, "risk_reward": 1.0})
    result = pipe.run(
        row,
        context={"data_valid": True, "data_fresh": True, "index_bullish": True},
        portfolio={"open_positions": 0, "max_open_positions": 5, "exposure_pct": 10},
        regime={"primary": "BULL"},
    )
    assert result["final_decision"] == "NO_TRADE"
    ev_stage = next(s for s in result["stages"] if s["stage"] == "EXPECTED_VALUE")
    assert ev_stage["status"] == StageStatus.FAIL.value


def test_pipeline_unknown_regime_blocks():
    pipe = FinalDecisionPipeline()
    row = _sample_row()
    result = pipe.run(
        row,
        context={"data_valid": True, "data_fresh": True},
        portfolio={"open_positions": 0, "max_open_positions": 5},
        regime={"primary": "UNKNOWN"},
    )
    assert result["final_decision"] == "NO_TRADE"
    assert result["critical_unknown"] is True


def test_committee_produces_eight_votes():
    committee = MasterTradingCommittee()
    votes = committee.evaluate(
        _sample_row(),
        context={"data_valid": True, "index_bullish": True},
        portfolio={"open_positions": 1, "max_open_positions": 5, "exposure_pct": 20, "daily_loss_pct": 0, "drawdown_pct": 1},
    )
    roles = {v.analyst for v in votes}
    assert "risk_manager" in roles
    assert "quant_analyst" in roles
    assert len(votes) >= 7


def test_session_mode_values():
    mode = current_session_mode()
    assert mode in {DeskSessionMode.PRE_MARKET, DeskSessionMode.INTRADAY, DeskSessionMode.POST_MARKET}


def test_profit_protection_partial_at_t1():
    from config.models import IndicatorSet

    ind = IndicatorSet(
        ema9=101, ema21=101, ema50=99, ema100=98, ema200=95,
        sma20=100, sma50=99, rsi14=55, macd=0.1, macd_signal=0.05, macd_hist=0.05,
        bb_upper=105, bb_middle=100, bb_lower=95, atr14=2.0, adx14=25,
        stoch_k=60, stoch_d=55, stoch_rsi_k=50, stoch_rsi_d=48,
        vwap=100, vol_sma20=1_000_000, momentum10=1, roc12=0.5, obv=1e6,
        mfi14=50, cmf20=0.1, cci20=10, williams_r=-30,
        support=97, resistance=105, pivot=100, structure="HH_HL",
    )
    state = initial_protect(100.0, 97.0)
    new_state, partial = update_profit_protection(
        entry=100.0,
        price=102.5,
        stop=97.0,
        ind=ind,
        t1=102.0,
        t2=104.0,
        t3=106.0,
        state=state,
        momentum_ok=True,
        cfg=replace(settings, tp1_exit_pct=0.33),
    )
    assert partial is not None
    assert partial > 0
    assert new_state.partial_exits_done[0] is True


def test_trading_service_desk_evaluate(monkeypatch):
    from strategy.service import TradingService

    svc = TradingService()
    monkeypatch.setattr(
        svc,
        "scan",
        lambda symbols=None: [],
    )
    # With empty scan, desk still returns structured NO_TRADE
    out = svc.desk_evaluate("THYAO")
    assert out["symbol"] == "THYAO"
    assert "pipeline" in out
    assert "committee_votes" in out


def test_desk_api_endpoints():
    from dashboard.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/api/desk/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "session_mode" in body

    r2 = client.get("/api/desk/evaluate/THYAO")
    assert r2.status_code == 200
    d = r2.json()
    assert d.get("symbol") == "THYAO"
    assert "decision" in d
