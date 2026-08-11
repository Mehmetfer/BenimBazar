"""Level 7 — autonomy governor, research/hypothesis/experiment, lab, diagnostics."""

from __future__ import annotations

from pathlib import Path

from level7.adversarial import AdversarialAgent
from level7.autonomy_governor import AutonomyGovernor
from level7.engine import Level7Engine
from level7.experiment import ExperimentEngine, PIPELINE
from level7.hypothesis import HypothesisEngine
from level7.memory import MemoryEngine
from level7.outcome import OutcomeAnalyzer
from level7.research import ResearchAgent
from level7.store import Level7Store
from level7.strategy_lab import ChampionChallenger, StrategyLab
from decision.engine import AIDecisionEngine
from decision.packet import DecisionMemory
from decision.watchlist import AIWatchlist
from strategy.service import TradingService


def test_autonomy_governor_emergency_on_kill(tmp_path: Path):
    g = AutonomyGovernor()
    v = g.evaluate(context={"data_valid": True, "data_fresh": True, "kill_switch": True})
    assert v.state == "EMERGENCY_STOP"
    assert v.allow_live is False
    assert v.allow_paper is False


def test_autonomy_governor_restricts_stale(tmp_path: Path):
    g = AutonomyGovernor()
    v = g.evaluate(
        context={"data_valid": True, "data_fresh": False, "data_kind": "LIVE", "kill_switch": False},
        system_health={"health_score": 90},
    )
    assert v.state == "OBSERVE"
    assert v.allow_paper is False


def test_research_hypothesis_experiment_pipeline(tmp_path: Path):
    store = Level7Store(path=tmp_path / "l7.db")
    research = ResearchAgent(store)
    hyps = HypothesisEngine(store)
    exps = ExperimentEngine(store, hyps)

    qs = research.propose_from_context(regime={"primary": "BULL"}, learning={"sample_size": 5, "sample_tier": "INSUFFICIENT"})
    assert qs
    assert research.list_questions()

    created = hyps.seed_from_research([q.to_dict() for q in qs[:1]])
    assert created
    h = created[0]
    assert h.status == "CREATED"

    exp = exps.start(h.id)
    assert exp.stage == "DATASET"
    # Advance with small N → BLOCKED at significance-sensitive stage eventually
    r = exps.advance(exp.id, passed=True, metrics={"sample_size": 5, "includes_fees": False})
    assert r["ok"]
    # Keep advancing until blocked or human
    eid = r["experiment"]["id"]
    for _ in range(8):
        cur = r["experiment"]
        if cur["status"] in {"BLOCKED", "AWAITING_HUMAN", "FAILED"}:
            break
        if cur["stage"] == "HUMAN_APPROVAL":
            break
        r = exps.advance(eid, passed=True, metrics={"sample_size": 5, "walk_forward_passed": False})
    # Small N should block before declaring winner
    assert r["experiment"]["status"] in {"BLOCKED", "RUNNING", "AWAITING_HUMAN", "FAILED"}
    assert "HUMAN_APPROVAL" in PIPELINE


def test_adversarial_refutes_buy():
    row = {
        "symbol": "THYAO",
        "final_decision": "STRONG_BUY",
        "scores": {"technical": 80, "volume": 40, "liquidity": 70},
        "mtf": {"15m": "BULL", "1d": "BEAR"},
        "opportunity": {"expected_value": 0.4, "risk_reward": 1.5},
    }
    out = AdversarialAgent().run(row, regime={"primary": "BEAR"}, action="STRONG_BUY").payload
    assert out["attacks"]
    assert any("WRONG" in a or "INVALIDATION" in a or "REFUTE" in a for a in out["attacks"])
    assert out["confidence_haircut"] >= 0


def test_memory_similarity_not_certainty(tmp_path: Path):
    store = Level7Store(path=tmp_path / "m.db")
    mem = MemoryEngine(store)
    row = {"symbol": "THYAO", "scores": {"technical": 70, "volume": 60, "liquidity": 80}, "opportunity": {"expected_value": 1, "risk_reward": 2}, "ai_confidence": 70, "regime": "BULL"}
    mem.remember_pattern(row=row, regime="BULL", outcome="WIN", sample_size=3)
    got = mem.retrieve_similar(row, regime="BULL")
    assert got["similarity_is_not_prediction"] is True
    assert got["memory_confidence"] < 0.5  # small N


def test_champion_promotion_blocked_without_evidence(tmp_path: Path):
    store = Level7Store(path=tmp_path / "s.db")
    lab = StrategyLab(store)
    arena = ChampionChallenger(lab, store)
    ch = lab.create_variant(base_name="Momentum", version="v2", params={"lookback": 20})
    out = arena.propose_promotion(ch["id"], metrics={"sample_size": 10, "sharpe": 1.2})
    assert out["ok"] is False
    assert "INSUFFICIENT_SAMPLE" in out["blockers"]


def test_human_promote_does_not_unlock_live(tmp_path: Path):
    store = Level7Store(path=tmp_path / "s2.db")
    lab = StrategyLab(store)
    arena = ChampionChallenger(lab, store)
    ch = lab.create_variant(base_name="Momentum", version="v3")
    # Force candidate status
    ch["status"] = "PROMOTION_CANDIDATE"
    store.upsert_row("strategies", ch)
    out = arena.human_approve_promotion(ch["id"], approved_by="tester")
    assert out["ok"] is True
    assert out["live_broker_unlocked"] is False


def test_outcome_root_cause_volume():
    rep = OutcomeAnalyzer().compare(
        predicted_direction="BUY",
        actual_direction="SELL",
        predicted_return=3.0,
        actual_return=-2.0,
        context={"volume_weak": True},
    )
    assert rep.error_class == "FALSE_BREAKOUT"
    assert "volume" in rep.root_cause.lower()


def test_level7_engine_cycle(tmp_path: Path):
    store = Level7Store(path=tmp_path / "e.db")
    eng = Level7Engine(TradingService(), store=store)
    out = eng.run_cycle(
        context={"data_valid": True, "data_fresh": True, "data_kind": "SIMULATED"},
        regime={"primary": "BULL", "labels": ["BULL", "RISK_ON"]},
        health={"health_score": 90},
        learning={"sample_tier": "INSUFFICIENT", "sample_size": 5},
        top_row={
            "symbol": "THYAO",
            "final_decision": "BUY",
            "scores": {"technical": 75, "volume": 70, "liquidity": 80},
            "mtf": {"1h": "BULL"},
            "opportunity": {"expected_value": 1.0, "risk_reward": 2.2},
            "price": 100,
            "stop": 95,
            "targets": [110],
        },
    )
    assert out["status"] == "OK"
    assert out["risk_bypass"] is False
    assert out["production_code_modified"] is False
    assert out["scorecard"]["full_level7_claimed"] is False
    assert out["autonomy"]["allow_live"] is False
    assert out["diagnostics"]["can_auto_promote_models"] is False
    assert out["research_questions"]
    assert out["hypotheses"]


def test_ai_decision_engine_embeds_level7(tmp_path: Path):
    trading = TradingService()
    eng = AIDecisionEngine(
        trading,
        memory=DecisionMemory(path=tmp_path / "d.db"),
        watchlist=AIWatchlist(path=tmp_path / "w.json"),
    )
    # Isolate L7 store
    eng.level7 = Level7Engine(trading, store=Level7Store(path=tmp_path / "l7.db"))
    out = eng.run_from_scan_rows(
        [
            {
                "symbol": "THYAO",
                "final_decision": "BUY",
                "buy_score": 78,
                "ai_confidence": 74,
                "opportunity": {"expected_value": 1.1, "risk_reward": 2.3, "expected_return_pct": 4.0, "expected_loss_pct": 1.5},
                "scores": {"liquidity": 80, "volume": 70, "technical": 75},
                "mtf": {"15m": "BULL", "1h": "BULL"},
                "price": 100,
                "stop": 95,
                "targets": [110],
                "regime": "BULL",
            }
        ],
        market_type="BIST",
    )
    assert out.get("level7")
    assert out["level7"].get("scorecard", {}).get("full_level7_claimed") is False
    assert out["command_center"].get("level7_score") is not None
