"""Level 8 — Continuous Learning Engine + §103 acceptance chain."""

from __future__ import annotations

from pathlib import Path

from level8.drift import DriftDetector
from level8.engine import ContinuousLearningEngine
from level8.experiment_factory import ExperimentFactory
from level8.knowledge import KnowledgeMemory
from level8.snapshots import DecisionSnapshotService
from level8.store import Level8Store
from decision.engine import AIDecisionEngine
from decision.packet import DecisionMemory
from decision.watchlist import AIWatchlist
from strategy.service import TradingService


def test_snapshot_rejects_mock(tmp_path: Path):
    store = Level8Store(path=tmp_path / "l8.db")
    snap = DecisionSnapshotService(store)
    out = snap.capture(symbol="THYAO", signal="BUY", data_kind="MOCK")
    assert out["ok"] is False


def test_replay_look_ahead_protected(tmp_path: Path):
    store = Level8Store(path=tmp_path / "l8.db")
    snap = DecisionSnapshotService(store)
    cap = snap.capture(
        symbol="THYAO",
        signal="BUY",
        data_kind="SIMULATED",
        features={"a": 1},
        confidence=70,
    )
    did = cap["snapshot"]["decision_id"]
    # Reject outcome before decision
    bad = snap.attach_outcome(did, outcome={"outcome_timestamp": "2000-01-01T00:00:00", "actual_return": 1})
    assert bad["ok"] is False
    assert bad["reason"] == "LOOK_AHEAD_REJECTED"
    ok = snap.attach_outcome(
        did,
        outcome={"outcome_timestamp": "2099-01-01T00:00:00", "actual_return": -1, "actual_direction": "SELL"},
        error_class="WRONG_DIRECTION",
        root_cause="test",
    )
    assert ok["ok"]
    replay = snap.replay(did)
    assert replay["look_ahead_protected"] is True
    assert "features" in replay["known_at_decision"]
    assert replay["actual_outcome"] is not None


def test_drift_derate_never_raises_risk(tmp_path: Path):
    store = Level8Store(path=tmp_path / "d.db")
    d = DriftDetector(store)
    d.detect_from_metrics(historical_win_rate=0.6, recent_win_rate=0.3, feature_shift=0.4)
    der = d.derate()
    assert der["risk_limits_increased"] is False
    assert der["size_mult"] < 1.0
    assert der["confidence_mult"] < 1.0


def test_knowledge_stale_not_deleted(tmp_path: Path):
    store = Level8Store(path=tmp_path / "k.db")
    km = KnowledgeMemory(store)
    rec = km.add(observation="volume helps", result="weak evidence", confidence=0.3)
    out = km.mark_stale(rec["id"])
    assert out["deleted"] is False
    assert out["knowledge"]["status"] == "STALE_KNOWLEDGE"


def test_promotion_score_blocks_small_n(tmp_path: Path):
    fac = ExperimentFactory(Level8Store(path=tmp_path / "f.db"))
    sc = fac.promotion_score({"sample_size": 5, "oos_sharpe": 2.0, "walk_forward_passed": True, "calibration_ok": True})
    assert sc["eligible_candidate"] is False
    assert "INSUFFICIENT_SAMPLE" in sc["blockers"]


def test_human_feedback_not_applied_to_params(tmp_path: Path):
    eng = ContinuousLearningEngine(store=Level8Store(path=tmp_path / "fb.db"))
    out = eng.add_human_feedback("D1", "BAD", note="missed stop")
    assert out["ok"]
    assert out["applied_to_model_params"] is False


def test_acceptance_chain_full(tmp_path: Path):
    """§103: decision→outcome→research→hypothesis→experiment→validate→propose (no auto promote)."""
    eng = ContinuousLearningEngine(TradingService(), store=Level8Store(path=tmp_path / "acc.db"))
    out = eng.run_acceptance_chain(data_kind="SIMULATED")
    assert out["status"] == "OK"
    assert out["snapshot"]
    assert out["outcome"]
    assert out["root_cause"]
    assert out["research"]
    assert out["hypothesis"]
    assert out["experiment"]["ok"]
    assert out["validation"]
    assert out["promotion"]
    assert out["auto_promoted"] is False
    assert out["risk_bypass"] is False
    assert out["broker_direct"] is False
    assert out["production_code_modified"] is False
    assert out["look_ahead_protected"] is True
    assert out["scorecard"]["full_level8_claimed"] is False
    assert out["scorecard"]["governance"]["risk_limits"] == "DENIED"
    assert out["scorecard"]["governance"]["kill_switch"] == "DENIED"
    assert out["scorecard"]["governance"]["auto_promotion"] is False
    # Replay works
    did = out["snapshot"]["decision_id"]
    replay = eng.snapshots.replay(did)
    assert replay["ok"]
    assert replay["look_ahead_protected"]


def test_ai_engine_embeds_level8(tmp_path: Path):
    trading = TradingService()
    eng = AIDecisionEngine(
        trading,
        memory=DecisionMemory(path=tmp_path / "d.db"),
        watchlist=AIWatchlist(path=tmp_path / "w.json"),
    )
    eng.level8 = ContinuousLearningEngine(trading, store=Level8Store(path=tmp_path / "l8.db"))
    # keep level7 isolated too if present
    if eng.level7 is not None:
        from level7.store import Level7Store
        from level7.engine import Level7Engine

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
    assert out.get("level8")
    assert out["level8"].get("scorecard", {}).get("full_level8_claimed") is False
    assert out["command_center"].get("level8_score") is not None
