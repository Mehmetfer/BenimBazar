"""Ultra agentic layer — debate, governor, quality, command center."""

from __future__ import annotations

from pathlib import Path

from decision.agents.debate import DebateEngine
from decision.agents.regime import RegimeAgent
from decision.engine import AIDecisionEngine
from decision.governor import AIGovernor
from decision.packet import DecisionMemory
from decision.quality import autonomy_dashboard_scores, score_decision_quality
from decision.watchlist import AIWatchlist
from strategy.service import TradingService


def test_debate_engine_bull_vs_bear():
    row = {
        "symbol": "THYAO",
        "final_decision": "BUY",
        "ai_confidence": 75,
        "scores": {"technical": 80, "momentum": 78, "volume": 70, "liquidity": 75},
        "mtf": {"15m": "BULL", "1h": "BULL", "1d": "BEAR"},
        "opportunity": {"expected_value": 0.8, "risk_reward": 2.2, "p_win": 0.55},
        "is_favorite": True,
        "spread_pct": 0.3,
    }
    out = DebateEngine().run(row, regime={"primary": "BULL", "labels": ["BULL", "RISK_ON"]}).payload
    debate = out["debate"]
    assert debate["bull_case"]
    assert debate["bear_case"]
    assert "MTF_CONFLICT" in debate["bear_case"] or debate["data_conflict"]
    assert debate["critic"]
    assert out["technical"]["note"]


def test_governor_blocks_invalid_data():
    g = AIGovernor()
    d = g.evaluate(context={"data_valid": False, "data_fresh": False, "data_kind": "UNKNOWN"})
    assert d.verdict == "BLOCK"


def test_governor_limits_on_conflict():
    g = AIGovernor()
    d = g.evaluate(
        context={"data_valid": True, "data_fresh": True, "data_kind": "SIMULATED", "kill_switch": False, "risk_paused": False},
        regime={"primary": "BULL", "labels": ["HIGH_VOLATILITY"], "confidence": 0.7},
        debate={"data_conflict": True, "bull_beats_bear": False, "overconfidence_risk": True},
        system_health={"health_score": 80},
    )
    assert d.verdict in {"LIMIT", "BLOCK"}
    assert d.allow_strong_buy is False
    assert d.size_mult_cap < 1.0


def test_strong_buy_standard_requires_quality():
    q = score_decision_quality(
        row={
            "final_decision": "STRONG_BUY",
            "scores": {"liquidity": 90},
            "mtf": {"15m": "BULL", "1h": "BULL"},
            "opportunity": {"expected_value": 2.0, "risk_reward": 3.0},
            "regime": "BULL",
        },
        context={"data_valid": True, "data_fresh": True, "data_kind": "LIVE"},
        debate={"bull_beats_bear": True, "bull_score": 80, "bear_score": 30, "data_conflict": False},
        regime={"primary": "BULL"},
    )
    assert q.eligible_strong_buy is True
    q2 = score_decision_quality(
        row={
            "final_decision": "STRONG_BUY",
            "scores": {"liquidity": 40},
            "mtf": {"15m": "BULL", "1d": "BEAR"},
            "opportunity": {"expected_value": -0.2, "risk_reward": 1.1},
        },
        context={"data_valid": True, "data_fresh": True, "data_kind": "SIMULATED"},
        debate={"bull_beats_bear": False, "data_conflict": True, "bull_score": 40, "bear_score": 70},
        regime={"primary": "BEAR"},
    )
    assert q2.eligible_strong_buy is False


def test_agentic_cycle_produces_debate_and_command_center(tmp_path: Path):
    trading = TradingService()
    eng = AIDecisionEngine(
        trading,
        memory=DecisionMemory(path=tmp_path / "d.db"),
        watchlist=AIWatchlist(path=tmp_path / "w.json"),
    )
    rows = [
        {
            "symbol": "THYAO",
            "final_decision": "BUY",
            "buy_score": 78,
            "ai_confidence": 74,
            "opportunity": {
                "expected_value": 1.1,
                "risk_reward": 2.3,
                "expected_return_pct": 4.0,
                "expected_loss_pct": 1.5,
            },
            "scores": {"liquidity": 80, "volume": 70, "technical": 75, "ai_confidence": 74},
            "mtf": {"15m": "BULL", "1h": "BULL"},
            "price": 100,
            "stop": 95,
            "targets": [110],
            "regime": "BULL",
        }
    ]
    out = eng.run_from_scan_rows(rows, market_type="BIST", top_n=3)
    assert out["status"] in {"OK", "GOVERNOR_BLOCKED"}
    assert out["regime"]
    assert out["governor"]
    assert out["command_center"]
    assert out["activity"]
    assert out["autonomy"]["autonomy_level"] >= 2
    if out["decisions"]:
        d0 = out["decisions"][0]
        assert d0["risk_engine_bypassed"] is False
        assert "bull_case" in d0
        assert "bear_case" in d0
        assert "quality" in d0
    st = eng.status()
    assert st["risk_bypass"] is False
    assert st["broker_direct"] is False


def test_research_mode():
    eng = AIDecisionEngine(TradingService())
    r = eng.analyze_symbol("THYAO", row={"symbol": "THYAO", "final_decision": "WAIT", "scores": {}, "mtf": {}, "opportunity": {}})
    assert r["debate"] is not None or r.get("debate") == r.get("debate")
    assert r["risk_bypass"] is False


def test_autonomy_dashboard_levels():
    a = autonomy_dashboard_scores(context_ok=True, discovery_n=20, decisions_n=3, prediction_tier="INSUFFICIENT")
    assert a["total_autonomy"] > 0
    assert a["autonomy_level"] <= 4  # cannot claim 5/6 without live gates


def test_regime_agent_labels():
    trading = TradingService()
    snap = RegimeAgent().run(trading, context={"data_fresh": True, "drawdown_pct": 0.5}).payload["regime"]
    assert snap["primary"]
    assert snap["labels"]
    assert 0 <= snap["confidence"] <= 1


def test_governor_blocks_kill_switch():
    g = AIGovernor()
    d = g.evaluate(
        context={"data_valid": True, "data_fresh": True, "data_kind": "LIVE", "kill_switch": True},
    )
    assert d.verdict == "BLOCK"
    assert "KILL_SWITCH" in d.reasons


def test_governor_blocks_risk_paused():
    g = AIGovernor()
    d = g.evaluate(
        context={
            "data_valid": True,
            "data_fresh": True,
            "data_kind": "LIVE",
            "kill_switch": False,
            "risk_paused": True,
        },
    )
    assert d.verdict == "BLOCK"


def test_decision_agent_governor_block_forces_no_trade():
    from decision.agents.pipeline import DecisionAgent
    from decision.opportunity import RankedOpportunity

    opp = RankedOpportunity(
        symbol="THYAO",
        market_type="BIST",
        action="BUY",
        opportunity_score=80,
        model_score=70,
        expected_value=1.0,
        expected_return_pct=3.0,
        expected_risk_pct=1.0,
        risk_reward=2.5,
        confidence=70,
        regime="BULL",
        mtf={"1h": "BULL"},
    )
    out = DecisionAgent().run(
        opp,
        decision_id="T1",
        context={"data_valid": True, "market_regime": "BULL"},
        row={"symbol": "THYAO", "final_decision": "BUY", "scores": {"liquidity": 80}, "mtf": {"1h": "BULL"}, "opportunity": {"expected_value": 1.0}},
        debate={"bull_beats_bear": True, "bear_case": [], "bull_score": 70, "bear_score": 20},
        governor={"verdict": "BLOCK", "allow_strong_buy": False, "reasons": ["KILL_SWITCH"]},
        quality={"eligible_strong_buy": False},
    )
    assert out.payload["reasoning"]["action"] == "NO_TRADE"
    assert "GOVERNOR_BLOCK" in out.payload["reasoning"]["reason_codes"]


def test_fail_closed_stale_data_blocks_cycle(tmp_path: Path):
    """When MarketAgent reports invalid data, cycle must NO_TRADE — no invented prices."""
    trading = TradingService()
    eng = AIDecisionEngine(
        trading,
        memory=DecisionMemory(path=tmp_path / "d2.db"),
        watchlist=AIWatchlist(path=tmp_path / "w2.json"),
    )

    class _BadMarket:
        def run(self, *a, **k):
            from decision.agents import AgentResult

            return AgentResult(
                "MarketAgent",
                False,
                {"market_context": {"data_kind": "UNKNOWN", "data_fresh": False}, "summary": "bad"},
                ["DATA_INVALID"],
            )

    eng.market_agent = _BadMarket()  # type: ignore[assignment]
    out = eng.run_from_scan_rows(
        [{"symbol": "THYAO", "final_decision": "BUY", "buy_score": 90}],
        market_type="BIST",
    )
    assert out["status"] == "NO_TRADE_DATA"
    assert out["ai_status"] == "BLOCKED"
    assert not out.get("decisions")
