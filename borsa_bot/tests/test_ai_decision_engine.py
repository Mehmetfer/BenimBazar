"""AI Decision Engine — context, ranking, reasoning, packets (Phases 1–4)."""

from __future__ import annotations

from pathlib import Path

from decision.context import build_context_pack
from decision.cost_governor import AICostGovernor
from decision.engine import AIDecisionEngine
from decision.opportunity import competitive_summary, opportunity_score_from_row, rank_opportunities
from decision.packet import DecisionMemory, build_decision_packet, new_decision_id
from decision.reason import reason_over_opportunity
from decision.watchlist import AIWatchlist
from strategy.service import TradingService


def test_context_pack_observes_without_invention():
    trading = TradingService()
    ctx = build_context_pack(trading, cycle_id="T1", market_type="BIST")
    d = ctx.to_dict()
    assert d["market_type"] == "BIST"
    assert d["market_regime"]
    assert "unknowns" in d
    assert ctx.note.startswith("Missing")


def test_opportunity_ranking_and_compare():
    rows = [
        {
            "symbol": "THYAO",
            "final_decision": "BUY",
            "buy_score": 70,
            "ai_confidence": 72,
            "opportunity": {"expected_value": 1.2, "risk_reward": 2.0, "expected_return_pct": 4.0, "expected_loss_pct": 1.5},
            "scores": {"liquidity": 80, "volume": 70},
            "mtf": {"15m": "BULL", "1h": "BULL", "1d": "BULL"},
            "is_favorite": True,
            "spread_pct": 0.2,
        },
        {
            "symbol": "ASELS",
            "final_decision": "BUY",
            "buy_score": 68,
            "ai_confidence": 65,
            "opportunity": {"expected_value": 0.4, "risk_reward": 1.6, "expected_return_pct": 3.0, "expected_loss_pct": 1.8},
            "scores": {"liquidity": 60, "volume": 55},
            "mtf": {"15m": "BULL", "1h": "BEAR", "1d": "BEAR"},
            "is_favorite": False,
            "spread_pct": 0.5,
        },
        {
            "symbol": "TUPRS",
            "final_decision": "WAIT",
            "buy_score": 50,
            "ai_confidence": 50,
            "opportunity": {"expected_value": -0.2, "risk_reward": 1.1},
            "scores": {"liquidity": 70},
            "mtf": {},
        },
    ]
    ranked = rank_opportunities(rows, top_n=3)
    assert ranked[0].symbol == "THYAO"
    assert ranked[0].rank == 1
    assert ranked[0].why_better
    summary = competitive_summary(ranked)
    assert summary["best"]["symbol"] == "THYAO"
    assert opportunity_score_from_row(rows[0]) > opportunity_score_from_row(rows[2])


def test_reason_negative_ev_no_trade():
    from decision.opportunity import RankedOpportunity

    opp = RankedOpportunity(
        symbol="X",
        market_type="BIST",
        action="BUY",
        opportunity_score=80,
        model_score=80,
        expected_value=-0.5,
        expected_return_pct=2.0,
        expected_risk_pct=3.0,
        risk_reward=0.8,
        confidence=80,
        regime="BULL",
        mtf={"15m": "BULL"},
        liquidity_ok=True,
        spread_ok=True,
    )
    r = reason_over_opportunity(opp, decision_id="D1", context={"data_valid": True, "market_regime": "BULL"})
    assert r.action == "NO_TRADE"
    assert "NEGATIVE_EXPECTED_VALUE" in r.reason_codes
    assert r.can_trade_proposal is False
    assert r.probability is None
    assert r.counter_argument


def test_reason_data_invalid():
    from decision.opportunity import RankedOpportunity

    opp = RankedOpportunity(
        symbol="Y",
        market_type="BIST",
        action="STRONG_BUY",
        opportunity_score=90,
        model_score=90,
        expected_value=2.0,
        expected_return_pct=5.0,
        expected_risk_pct=1.0,
        risk_reward=3.0,
        confidence=90,
        regime="BULL",
        liquidity_ok=True,
        spread_ok=True,
    )
    r = reason_over_opportunity(opp, decision_id="D2", context={"data_valid": False})
    assert r.action == "NO_TRADE"
    assert r.can_trade_proposal is False


def test_decision_memory_and_watchlist(tmp_path: Path):
    mem = DecisionMemory(path=tmp_path / "dec.db")
    wl = AIWatchlist(path=tmp_path / "wl.json")
    trading = TradingService()
    eng = AIDecisionEngine(trading, memory=mem, watchlist=wl)
    rows = [
        {
            "symbol": "THYAO",
            "final_decision": "BUY",
            "buy_score": 75,
            "ai_confidence": 70,
            "opportunity": {"expected_value": 1.0, "risk_reward": 2.0, "expected_return_pct": 3.5, "expected_loss_pct": 1.2},
            "scores": {"liquidity": 75, "volume": 65, "ai_confidence": 70},
            "mtf": {"15m": "BULL", "1h": "BULL"},
            "price": 100,
            "stop": 95,
            "targets": [110],
            "regime": "BULL",
        }
    ]
    out = eng.run_from_scan_rows(rows, market_type="BIST", top_n=3)
    assert out["status"] == "OK"
    assert out["ai_status"] == "ACTIVE"
    assert out["top_card"]["risk_bypass"] is False if "risk_bypass" in out["top_card"] else True
    assert mem.recent(limit=5)
    assert wl.list_items()
    assert eng.status()["risk_bypass"] is False
    assert eng.status()["broker_direct"] is False


def test_cost_governor_blocks_burst():
    g = AICostGovernor(max_calls_per_minute=2, max_calls_per_hour=10)
    assert g.allow().allowed
    assert g.allow().allowed
    blocked = g.allow()
    assert blocked.allowed is False


def test_packet_never_bypasses_risk():
    from decision.context import ContextPack
    from decision.opportunity import RankedOpportunity
    from decision.reason import ReasoningResult

    ctx = ContextPack(
        cycle_id="c",
        market_type="BIST",
        observed_at="t",
        market_regime="BULL",
        data_kind="SIMULATED",
        data_fresh=True,
        data_connected=True,
        provider_class="SIMULATED",
        market_session="OPEN",
        equity=1.0,
        cash=1.0,
        open_positions=0,
        daily_pnl=0.0,
        drawdown_pct=0.0,
        risk_paused=False,
        kill_switch=False,
        capital_mode="NORMAL",
        prediction_tier="INSUFFICIENT",
        prediction_sample=0,
    )
    opp = RankedOpportunity(
        symbol="THYAO",
        market_type="BIST",
        action="BUY",
        opportunity_score=70,
        model_score=70,
        expected_value=1.0,
        expected_return_pct=3.0,
        expected_risk_pct=1.0,
        risk_reward=2.0,
        confidence=70,
        regime="BULL",
    )
    reasoning = ReasoningResult(
        decision_id=new_decision_id(),
        symbol="THYAO",
        market_type="BIST",
        action="BUY",
        confidence=70,
        probability=None,
        model_score=70,
        opportunity_score=70,
        expected_value=1.0,
        expected_return_pct=3.0,
        expected_risk_pct=1.0,
        risk_reward=2.0,
        regime="BULL",
        strategy="TREND_FOLLOWING",
        mtf_label="MTF_ALIGNED_BULLISH",
        reason_codes=["TREND_CONFIRMED"],
        can_trade_proposal=True,
    )
    pkt = build_decision_packet(reasoning=reasoning, context=ctx, opportunity=opp, row={"price": 100, "stop": 95, "targets": [110]})
    assert pkt.risk_engine_bypassed is False
    assert pkt.probability is None
