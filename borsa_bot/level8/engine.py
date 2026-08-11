"""ContinuousLearningEngine — OBSERVE→…→PROPOSE loop (no production mutation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

from level7.outcome import OutcomeAnalyzer, RootCauseEngine
from level7.research import ResearchAgent
from level7.hypothesis import HypothesisEngine
from level7.memory import MemoryEngine
from level8.drift import DriftDetector
from level8.experiment_factory import ExperimentFactory
from level8.knowledge import KnowledgeMemory
from level8.reports import LearningReports, ResearchBudget
from level8.scores import level8_scorecard
from level8.snapshots import DecisionSnapshotService
from level8.store import Level8Store


@dataclass
class ContinuousLearningReport:
    cycle_id: str
    period: str
    status: str
    snapshot: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    root_cause: dict[str, Any] | None = None
    research: list[dict[str, Any]] = field(default_factory=list)
    hypothesis: dict[str, Any] | None = None
    experiment: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    promotion: dict[str, Any] | None = None
    drift: dict[str, Any] = field(default_factory=dict)
    derate: dict[str, Any] = field(default_factory=dict)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] | None = None
    scorecard: dict[str, Any] = field(default_factory=dict)
    risk_bypass: bool = False
    broker_direct: bool = False
    production_code_modified: bool = False
    auto_promoted: bool = False
    look_ahead_protected: bool = True
    note: str = (
        "Continuous learning proposes improvements only. "
        "No risk/kill-switch/broker mutation. No auto champion promotion."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContinuousLearningEngine:
    def __init__(self, trading: Any | None = None, *, store: Optional[Level8Store] = None) -> None:
        self.trading = trading
        self.store = store or Level8Store()
        self.snapshots = DecisionSnapshotService(self.store)
        self.outcomes = OutcomeAnalyzer(self.store.l7)
        self.root_cause = RootCauseEngine()
        self.research = ResearchAgent(self.store.l7)
        self.hypotheses = HypothesisEngine(self.store.l7)
        self.factory = ExperimentFactory(self.store)
        self.drift = DriftDetector(self.store)
        self.knowledge = KnowledgeMemory(self.store)
        self.reports = LearningReports(self.store)
        self.budget = ResearchBudget(self.store)
        self.patterns = MemoryEngine(self.store.l7)
        self._last: ContinuousLearningReport | None = None

    def status(self) -> dict[str, Any]:
        last = self._last.to_dict() if self._last else None
        return {
            "last_cycle": last,
            "scorecard": (last or {}).get("scorecard"),
            "open_drifts": self.drift.list_open(20),
            "knowledge_active": self.knowledge.list_active(10),
            "snapshots": self.snapshots.list_recent(10),
            "reports": self.reports.list_reports(limit=10),
            "budget": self.budget._row(),
            "risk_bypass": False,
            "broker_direct": False,
            "auto_promotion": False,
            "full_level8_claimed": False,
            "note": "WHEN UNCERTAIN → DO NOT TRADE · correlation ≠ causation",
        }

    def run_period(
        self,
        period: str = "HOURLY",
        *,
        context: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        period = period.upper()
        metrics = metrics or {}
        context = context or {}
        if period == "HOURLY":
            rep = self.reports.hourly(metrics)
        elif period == "DAILY":
            rep = self.reports.daily(metrics)
        elif period == "WEEKLY":
            rep = self.reports.weekly(metrics)
        elif period == "MONTHLY":
            rep = self.reports.monthly(metrics)
        else:
            rep = self.reports.autonomous_research_report(metrics)

        # Drift check from metrics if provided
        events = self.drift.detect_from_metrics(
            feature_shift=metrics.get("feature_shift"),
            concept_shift=metrics.get("concept_shift"),
            historical_win_rate=metrics.get("historical_win_rate"),
            recent_win_rate=metrics.get("recent_win_rate"),
        )
        derate = self.drift.derate()
        scorecard = self._scorecard(context=context)
        out = ContinuousLearningReport(
            cycle_id=f"CL-{uuid4().hex[:10]}",
            period=period,
            status="OK",
            report=rep,
            drift={"events": events, "open": self.drift.list_open(10)},
            derate=derate,
            scorecard=scorecard,
        )
        self._last = out
        return out.to_dict()

    def run_acceptance_chain(
        self,
        *,
        symbol: str = "THYAO",
        market_type: str = "BIST",
        signal: str = "BUY",
        features: dict | None = None,
        actual_direction: str = "SELL",
        actual_return: float = -2.0,
        predicted_return: float = 3.0,
        data_kind: str = "SIMULATED",
        force_metrics: dict | None = None,
    ) -> dict[str, Any]:
        """Full §103 acceptance path — ends at PROMOTION_CANDIDATE or blocked; never auto-promotes."""
        cycle_id = f"CL-ACC-{uuid4().hex[:8]}"
        report = ContinuousLearningReport(cycle_id=cycle_id, period="ACCEPTANCE", status="RUNNING")

        features = features or {
            "trend_momentum": 0.75,
            "volume_confirmation": 0.35,
            "mtf_conflict": True,
            "liquidity": 0.8,
        }

        # 1–2 Decision + snapshot
        snap = self.snapshots.capture(
            symbol=symbol,
            market_type=market_type,
            signal=signal,
            confidence=72.0,
            uncertainty="HIGH",
            expected_value=1.1,
            entry=100.0,
            stop=95.0,
            target=110.0,
            regime="BULL",
            timeframe="15m",
            features=features,
            indicators={"rsi_family": "bucketed", "macd_family": "bucketed"},
            data_kind=data_kind,
            provider="acceptance_test",
            market_snapshot={"price": 100.0, "spread_pct": 0.2},
        )
        if not snap.get("ok"):
            report.status = "SNAPSHOT_REJECTED"
            report.snapshot = snap
            self._last = report
            return report.to_dict()
        report.snapshot = snap["snapshot"]
        did = snap["snapshot"]["decision_id"]

        # 3–6 Outcome + classify + root cause
        oc = self.outcomes.compare(
            predicted_direction=signal,
            actual_direction=actual_direction,
            predicted_return=predicted_return,
            actual_return=actual_return,
            context={
                "volume_weak": float(features.get("volume_confirmation") or 0) < 0.55,
                "mtf_conflict": bool(features.get("mtf_conflict")),
                "data_conflict": bool(features.get("mtf_conflict")),
                "regime": "BULL",
            },
        )
        rc = self.root_cause.explain(oc)
        report.outcome = oc.to_dict()
        report.root_cause = rc
        self.snapshots.attach_outcome(
            did,
            outcome={
                "predicted_direction": signal,
                "actual_direction": actual_direction,
                "predicted_return": predicted_return,
                "actual_return": actual_return,
                "direction_correct": oc.direction_correct,
                "outcome_timestamp": snap["snapshot"]["timestamp"],  # same-second ok for test; real systems use later ts
                "simulated": data_kind.upper() == "SIMULATED",
            },
            error_class=oc.error_class,
            root_cause=oc.root_cause,
        )

        # Replay check (look-ahead protected)
        replay = self.snapshots.replay(did)
        assert replay.get("look_ahead_protected") is True

        # 7 Research question
        qs = self.research.propose_from_context(
            regime={"primary": "BULL"},
            learning={"sample_size": 5, "sample_tier": "INSUFFICIENT"},
            debate_stats={"conflict_rate": 0.4},
        )
        report.research = [q.to_dict() for q in qs[:3]]

        # 8 Hypothesis from failure
        hyp = self.hypotheses.create(
            title=f"H-ACC-{cycle_id[-6:]}",
            statement=(
                "When 15m breakout lacks volume confirmation and 1h/1d conflict, "
                "continuation success rate decreases versus volume-confirmed aligned setups."
            ),
            regime="HIGH_VOLATILITY",
            timeframe="15m+1h",
            params={"from_error": oc.error_class},
        )
        report.hypothesis = hyp.to_dict()

        # Budget gate
        bud = self.budget.allow(experiments=1, api_calls=1, model_calls=1)
        if not bud.get("allowed"):
            report.status = "BUDGET_BLOCKED"
            report.scorecard = self._scorecard()
            self._last = report
            return report.to_dict()

        # 9 Experiment factory
        plan = self.factory.create_from_hypothesis(hyp.id, dataset="historical_bars", market_types=[market_type])
        if not plan.get("ok"):
            report.status = "FACTORY_REJECTED"
            report.experiment = plan
            report.scorecard = self._scorecard()
            self._last = report
            return report.to_dict()
        report.experiment = plan

        eid = plan["experiment"]["id"]
        # 10–15 validation chain
        metrics = force_metrics or {
            "DATASET": {"sample_size": 80, "n": 80},
            "BACKTEST": {"sample_size": 80, "backtest_sharpe": 1.1, "n_parameters": 4},
            "WALK_FORWARD": {"sample_size": 60, "walk_forward_passed": True, "sharpe": 0.9},
            "OUT_OF_SAMPLE": {"sample_size": 50, "oos_sharpe": 0.85, "calibration_ok": True, "regime_robust": True},
            "PAPER": {"sample_size": 40, "sharpe": 0.8},
            "SHADOW": {"sample_size": 40, "sharpe": 0.82, "stability": 0.7, "risk_adjusted_return": 0.75},
            "EVALUATION": {
                "sample_size": 50,
                "oos_sharpe": 0.85,
                "walk_forward_passed": True,
                "calibration_ok": True,
                "regime_robust": True,
                "stability": 0.7,
                "risk_adjusted_return": 0.75,
                "max_drawdown_pct": 12,
                "n_parameters": 4,
            },
        }
        validation = self.factory.run_validation_chain(eid, metrics_by_stage=metrics)
        report.validation = validation

        # Compare / promotion score (propose only)
        eval_metrics = metrics.get("EVALUATION") or {}
        promo_score = self.factory.promotion_score(eval_metrics)
        challenger_id = (plan.get("plan") or {}).get("challenger", {}).get("id")
        promo: dict[str, Any] = {"score": promo_score, "challenger_id": challenger_id}
        if promo_score.get("eligible_candidate") and challenger_id:
            # Mark challenger performance then propose — still needs human
            self.factory.lab.update_performance(challenger_id, eval_metrics)
            proposed = self.factory.arena.propose_promotion(challenger_id, metrics=eval_metrics)
            promo["proposal"] = proposed
            # Explicit: do NOT call human_approve_promotion here
            promo["auto_promoted"] = False
            promo["awaits_human"] = True
        else:
            promo["proposal"] = {"ok": False, "reason": "NOT_ELIGIBLE", "blockers": promo_score.get("blockers")}
            promo["auto_promoted"] = False
        report.promotion = promo
        report.auto_promoted = False

        # Knowledge + patterns
        self.knowledge.add(
            observation=f"Failure on {symbol}: {oc.error_class}",
            result=oc.root_cause,
            confidence=0.45,
            hypothesis_id=hyp.id,
            experiment_id=eid,
            evidence={"error_class": oc.error_class, "correlation_not_causation": True},
        )
        self.patterns.remember_pattern(
            row={"symbol": symbol, "scores": {"technical": 75, "volume": 35, "liquidity": 80}, "opportunity": {"expected_value": 1.1, "risk_reward": 2}, "ai_confidence": 72, "regime": "BULL"},
            regime="BULL",
            outcome="LOSS",
            sample_size=1,
        )
        report.knowledge = self.knowledge.list_active(5)

        # Drift from repeated failure signal
        self.drift.detect_from_metrics(historical_win_rate=0.62, recent_win_rate=0.38)
        report.drift = {"open": self.drift.list_open(10)}
        report.derate = self.drift.derate()

        # Research report
        report.report = self.reports.autonomous_research_report(
            {
                "what_changed": "Acceptance chain executed",
                "what_learned": oc.lesson,
                "what_failed": oc.root_cause,
                "what_succeeded": "Look-ahead-protected snapshot/replay",
                "hypotheses_pending": [hyp.id],
                "experiments_running": [eid],
                "promote": [challenger_id] if promo_score.get("eligible_candidate") else [],
                "reject": [],
            }
        )

        report.scorecard = self._scorecard()
        report.status = "OK"
        self._last = report
        self.store.audit(agent="ContinuousLearningEngine", action="ACCEPTANCE_CHAIN", reason=cycle_id, payload={"decision_id": did})
        return report.to_dict()

    def add_human_feedback(self, decision_id: str, label: str, *, note: str = "") -> dict:
        label = label.upper()
        if label not in {"GOOD", "BAD", "IGNORE"}:
            return {"ok": False, "reason": "invalid_label"}
        from uuid import uuid4 as _u

        rec = {
            "id": f"FB-{_u().hex[:10]}",
            "decision_id": decision_id,
            "label": label,
            "note": note,
            "created_at": __import__("config.models", fromlist=["utc_now"]).utc_now().isoformat(),
            "aggregated": 0,
        }
        self.store.upsert("human_feedback", rec)
        # Safety: do not write into model params
        return {"ok": True, "feedback": rec, "applied_to_model_params": False, "note": "Feedback stored for aggregate→validate→experiment only"}

    def _scorecard(self, context: dict | None = None) -> dict[str, Any]:
        context = context or {}
        experiments = self.store.l7.count("experiments")
        hyps = self.store.l7.list_rows("hypotheses", limit=200)
        validated = sum(1 for h in hyps if h.get("status") in {"PAPER", "SHADOW", "PROMOTION_CANDIDATE"})
        rejected = sum(1 for h in hyps if h.get("status") == "REJECTED")
        chall = self.store.l7.count("strategies", where="role=?", params=("CHALLENGER",))
        promo = self.store.l7.count("strategies", where="status=?", params=("PROMOTION_CANDIDATE",))
        drifts = self.store.count("drift_events", where="status=?", params=("OPEN",))
        patterns = self.store.l7.count("pattern_memory")
        roots = self.store.count("decision_snapshots", where="root_cause IS NOT NULL AND root_cause != ''")
        data_q = 95.0 if context.get("data_valid") else 70.0
        if str(context.get("data_kind") or "").upper() == "SIMULATED":
            data_q = min(data_q, 70.0)
        return level8_scorecard(
            data_integrity=data_q,
            research_score=min(95.0, 45 + self.store.l7.count("research_questions") * 3 + len(hyps) * 2),
            self_diagnostic=80.0,
            model_adaptation=min(70.0, 40 + chall * 5 + promo * 8),
            strategy_adaptation=min(70.0, 40 + experiments * 2),
            risk_safety=96.0,
            learning_loop_ok=True,
            prediction_tier=str(context.get("prediction_tier") or "INSUFFICIENT"),
            experiments=experiments,
            validated_hypotheses=validated,
            rejected_hypotheses=rejected,
            active_challengers=chall,
            promotion_candidates=promo,
            drifts=drifts,
            patterns=patterns,
            root_causes=roots,
        )


def level8_report(engine: ContinuousLearningEngine) -> dict[str, Any]:
    return engine.status()
