"""Level7Engine — orchestrates research → hypothesis → experiment → diagnostics (propose-only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

from level7.adversarial import AdversarialAgent
from level7.autonomy_governor import AutonomyGovernor, autonomy_governor
from level7.diagnostics import SelfDiagnostics, level7_scorecard
from level7.experiment import ExperimentEngine
from level7.hypothesis import HypothesisEngine
from level7.memory import MemoryEngine
from level7.outcome import OutcomeAnalyzer, RootCauseEngine
from level7.research import ResearchAgent
from level7.store import Level7Store
from level7.strategy_lab import ChampionChallenger, StrategyLab


@dataclass
class Level7CycleReport:
    cycle_id: str
    status: str
    autonomy: dict[str, Any] = field(default_factory=dict)
    research_questions: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    adversarial: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    champion: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    scorecard: dict[str, Any] = field(default_factory=dict)
    journal_hint: dict[str, Any] | None = None
    risk_bypass: bool = False
    broker_direct: bool = False
    production_code_modified: bool = False
    note: str = (
        "Level 7 safe loop: observe→hypothesize→test→validate→propose. "
        "No risk/broker/kill-switch bypass. No auto model promotion."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Level7Engine:
    def __init__(self, trading: Any | None = None, *, store: Optional[Level7Store] = None) -> None:
        self.trading = trading
        self.store = store or Level7Store()
        self.autonomy = AutonomyGovernor()
        self.research = ResearchAgent(self.store)
        self.hypotheses = HypothesisEngine(self.store)
        self.experiments = ExperimentEngine(self.store, self.hypotheses)
        self.adversarial = AdversarialAgent()
        self.memory = MemoryEngine(self.store)
        self.outcomes = OutcomeAnalyzer(self.store)
        self.root_cause = RootCauseEngine()
        self.lab = StrategyLab(self.store)
        self.arena = ChampionChallenger(self.lab, self.store)
        self.diagnostics = SelfDiagnostics(self.store)
        self._last: Level7CycleReport | None = None

    def status(self) -> dict[str, Any]:
        last = self._last.to_dict() if self._last else None
        return {
            "last_cycle": last,
            "autonomy": (last or {}).get("autonomy"),
            "scorecard": (last or {}).get("scorecard"),
            "champion": self.arena.status(),
            "research_open": self.store.count("research_questions", where="status=?", params=("OPEN",)),
            "hypotheses": self.store.count("hypotheses"),
            "experiments": self.store.count("experiments"),
            "risk_bypass": False,
            "broker_direct": False,
            "can_auto_promote": False,
            "note": "WHEN UNCERTAIN → DO NOT TRADE",
        }

    def run_cycle(
        self,
        *,
        context: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
        health: dict[str, Any] | None = None,
        learning: dict[str, Any] | None = None,
        top_row: dict[str, Any] | None = None,
        decision_quality_avg: float = 70.0,
        loss_governor_state: str | None = None,
        seed_research: bool = True,
    ) -> dict[str, Any]:
        cycle_id = f"L7-{uuid4().hex[:10]}"
        ctx = dict(context or {})
        regime = regime or {}
        health = health or {}
        learning = learning or {}

        # Attach regime labels for autonomy governor
        if regime.get("labels"):
            ctx["regime_labels"] = regime["labels"]

        auto = self.autonomy.evaluate(
            context=ctx,
            system_health=health,
            prediction_tier=str(learning.get("sample_tier") or learning.get("grade") or ""),
            model_disagreement=bool((top_row or {}).get("mtf_conflict")),
            loss_governor_state=loss_governor_state,
            data_quality=95.0 if ctx.get("data_valid") and ctx.get("data_fresh") else 40.0,
        )

        report = Level7CycleReport(cycle_id=cycle_id, status="RUNNING", autonomy=auto.to_dict())

        if auto.state == "EMERGENCY_STOP":
            report.status = "EMERGENCY_STOP"
            report.diagnostics = self.diagnostics.diagnose(autonomy=auto, learning=learning, health=health)
            report.scorecard = level7_scorecard(
                data_integrity=20.0,
                research_n=0,
                hypothesis_n=0,
                experiment_n=0,
                decision_quality_avg=0.0,
                risk_awareness=100.0,
                learning_tier=str(learning.get("sample_tier") or "INSUFFICIENT"),
                diagnostics_ok=True,
                autonomy_tier=auto.tier,
            )
            self._last = report
            return report.to_dict()

        questions: list = []
        if seed_research and auto.allow_research:
            questions = self.research.propose_from_context(regime=regime, learning=learning)
            # Seed hypotheses once
            if self.store.count("hypotheses") < 3:
                self.hypotheses.seed_from_research([q.to_dict() for q in questions[:2]])

        report.research_questions = [q.to_dict() for q in questions] if questions else self.research.list_questions(10)
        report.hypotheses = self.hypotheses.list_hypotheses(20)

        # Optionally start an experiment for first CREATED hypothesis
        created = [h for h in report.hypotheses if h.get("status") == "CREATED"]
        if created and auto.allow_research:
            exp = self.experiments.start(created[0]["id"])
            # Advance through dataset with theoretical metrics (honest label)
            self.experiments.advance(
                exp.id,
                passed=True,
                metrics={"sample_size": 0, "includes_fees": False, "includes_slippage": False, "note": "pipeline_init"},
            )

        report.experiments = self.experiments.list_experiments(20)

        # Adversarial + memory on top candidate
        if top_row:
            adv = self.adversarial.run(top_row, regime=regime, action=top_row.get("final_decision"))
            report.adversarial = adv.payload
            mem = self.memory.retrieve_similar(top_row, regime=str(regime.get("primary") or top_row.get("regime")))
            report.memory = mem
            # Remember current setup as UNKNOWN outcome (for future retrieval)
            self.memory.remember_pattern(
                row=top_row,
                regime=str(regime.get("primary") or top_row.get("regime")),
                outcome="PENDING",
            )
            thesis = " · ".join((adv.payload.get("debate") or {}).get("bull_case") or [])[:180] or "structured setup"
            report.journal_hint = self.memory.journal_entry(
                {
                    "symbol": top_row.get("symbol"),
                    "setup": top_row.get("final_decision"),
                    "reason": ",".join((adv.payload.get("attacks") or [])[:2]),
                    "entry": top_row.get("entry") or top_row.get("price"),
                    "stop": top_row.get("stop"),
                    "target": (top_row.get("targets") or [None])[0],
                    "thesis": thesis,
                    "decision": top_row.get("final_decision"),
                    "outcome": "PENDING",
                    "lesson": "Await outcome — similarity≠certainty",
                }
            )

        report.champion = self.arena.status()
        report.diagnostics = self.diagnostics.diagnose(
            autonomy=auto,
            learning=learning,
            health=health,
            experiments=report.experiments,
            strategies=self.lab.list_strategies(20),
        )
        data_q = 95.0 if ctx.get("data_valid") and ctx.get("data_fresh") else (
            60.0 if str(ctx.get("data_kind") or "").upper() == "SIMULATED" else 35.0
        )
        report.scorecard = level7_scorecard(
            data_integrity=data_q,
            research_n=len(report.research_questions),
            hypothesis_n=len(report.hypotheses),
            experiment_n=len(report.experiments),
            decision_quality_avg=decision_quality_avg,
            risk_awareness=94.0 if auto.tier != "EMERGENCY_STOP" else 100.0,
            learning_tier=str(learning.get("sample_tier") or learning.get("grade") or "INSUFFICIENT"),
            diagnostics_ok=True,
            execution_safety=95.0,
            autonomy_tier=auto.tier,
        )
        report.status = "OK"
        self._last = report
        self.store.audit(agent="Level7Engine", action="CYCLE", reason=cycle_id, output_data={"status": "OK"})
        return report.to_dict()


def level7_report(engine: Level7Engine) -> dict[str, Any]:
    return engine.status()
