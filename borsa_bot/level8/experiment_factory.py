"""ExperimentFactory — hypothesis → isolated sandbox experiment (reuses Level 7)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.experiment import ExperimentEngine, PIPELINE
from level7.hypothesis import HypothesisEngine
from level7.strategy_lab import ChampionChallenger, StrategyLab
from level8.store import Level8Store


class ExperimentFactory:
    agent_id = "ExperimentFactory"

    def __init__(self, store: Level8Store | None = None) -> None:
        self.store = store or Level8Store()
        self.hypotheses = HypothesisEngine(self.store.l7)
        self.experiments = ExperimentEngine(self.store.l7, self.hypotheses)
        self.lab = StrategyLab(self.store.l7)
        self.arena = ChampionChallenger(self.lab, self.store.l7)
        self._trial_count = 0

    def quality_filter(self, hypothesis: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        ok = True
        stmt = str(hypothesis.get("statement") or hypothesis.get("question") or "")
        if len(stmt) < 20:
            ok = False
            reasons.append("NOT_TESTABLE_TOO_SHORT")
        if "guaranteed" in stmt.lower() or "100%" in stmt:
            ok = False
            reasons.append("UNFALSIFIABLE_GUARANTEE_LANGUAGE")
        # Novelty: reject exact duplicate titles recently
        title = str(hypothesis.get("title") or "")
        if title:
            existing = self.store.l7.list_rows("hypotheses", where="title=?", params=(title,), limit=1)
            if existing and existing[0].get("id") != hypothesis.get("id"):
                ok = False
                reasons.append("NOT_NOVEL")
        return {
            "ok": ok,
            "novelty_ok": "NOT_NOVEL" not in reasons,
            "testability_ok": "NOT_TESTABLE_TOO_SHORT" not in reasons and "UNFALSIFIABLE_GUARANTEE_LANGUAGE" not in reasons,
            "leakage_risk": "LOW",
            "reasons": reasons or ["ok"],
        }

    def create_from_hypothesis(
        self,
        hypothesis_id: str,
        *,
        dataset: str = "historical_bars",
        market_types: list[str] | None = None,
        timeframes: list[str] | None = None,
        regimes: list[str] | None = None,
    ) -> dict[str, Any]:
        hyp = self.store.l7.list_rows("hypotheses", where="id=?", params=(hypothesis_id,), limit=1)
        if not hyp:
            return {"ok": False, "reason": "hypothesis_not_found"}
        qf = self.quality_filter(hyp[0])
        if not qf["ok"]:
            self.store.audit(agent=self.agent_id, action="QUALITY_REJECT", reason=hypothesis_id, payload=qf, result="REJECTED")
            return {"ok": False, "reason": "HYPOTHESIS_QUALITY_FILTER", "filter": qf}

        self._trial_count += 1
        exp = self.experiments.start(hypothesis_id, dataset=dataset)
        champion = self.arena.status().get("champion")
        # Challenger variant in sandbox
        challenger = self.lab.create_variant(
            base_name=str((champion or {}).get("name") or "HeuristicEnsemble"),
            version=f"challenger-{uuid4().hex[:6]}",
            params={
                "hypothesis_id": hypothesis_id,
                "sandbox": True,
                "baseline_champion_id": (champion or {}).get("id"),
                "market_types": market_types or ["BIST"],
                "timeframes": timeframes or ["15m", "1h", "1d"],
                "regimes": regimes or ["BULL", "BEAR", "SIDEWAYS", "HIGH_VOLATILITY", "LOW_VOLATILITY"],
                "isolation": "SANDBOX",
            },
        )
        plan = {
            "experiment_id": exp.id,
            "hypothesis_id": hypothesis_id,
            "baseline": champion,
            "challenger": challenger,
            "control_vs_experiment": True,
            "pipeline": list(PIPELINE),
            "walk_forward": {"train": True, "validation": True, "test": True, "rolling": True},
            "out_of_sample_required": True,
            "number_of_trials": self._trial_count,
            "dataset": dataset,
            "selection_method": "pre_registered_hypothesis",
            "theoretical": True,
            "production_isolated": True,
            "created_at": utc_now().isoformat(),
        }
        self.store.audit(agent=self.agent_id, action="FACTORY_CREATE", reason=hypothesis_id, payload={"experiment_id": exp.id})
        return {"ok": True, "plan": plan, "experiment": exp.to_dict()}

    def run_validation_chain(
        self,
        experiment_id: str,
        *,
        metrics_by_stage: dict[str, dict] | None = None,
    ) -> dict[str, Any]:
        """Advance through BACKTEST→WF→OOS→PAPER→SHADOW→EVAL with guards."""
        metrics_by_stage = metrics_by_stage or {}
        history: list[dict] = []
        # Ensure we start from DATASET
        stages_to_run = ["DATASET", "BACKTEST", "WALK_FORWARD", "OUT_OF_SAMPLE", "PAPER", "SHADOW", "EVALUATION"]
        current = self.store.l7.list_rows("experiments", where="id=?", params=(experiment_id,), limit=1)
        if not current:
            return {"ok": False, "reason": "experiment_not_found"}

        eid = experiment_id
        for stage_hint in stages_to_run:
            cur = self.store.l7.list_rows("experiments", where="id=?", params=(eid,), limit=1)[0]
            if cur.get("status") in {"FAILED", "BLOCKED", "AWAITING_HUMAN"}:
                history.append(cur)
                break
            if cur.get("stage") == "HUMAN_APPROVAL":
                history.append(cur)
                break
            m = dict(metrics_by_stage.get(cur.get("stage") or stage_hint) or metrics_by_stage.get(stage_hint) or {})
            # Default metrics if not provided — honest theoretical + sample awareness
            m.setdefault("sample_size", m.get("n", 0))
            m.setdefault("includes_fees", False)
            m.setdefault("includes_slippage", False)
            # Do NOT rubber-stamp validation — require explicit True in stage metrics
            if "walk_forward_passed" not in m:
                m["walk_forward_passed"] = False
            if "calibration_ok" not in m:
                m["calibration_ok"] = False
            m.setdefault("oos_sharpe", m.get("sharpe", 0.0))
            m.setdefault("max_drawdown_pct", 100.0)
            m.setdefault("overfit_risk", self._overfit_score(m))
            # Multiple-testing metadata
            m["number_of_trials"] = self._trial_count
            m["bonferroni_hint"] = round(0.05 / max(1, self._trial_count), 5)

            # Block advance through WF/OOS/EVAL without explicit validation flags
            stage_now = str(cur.get("stage") or stage_hint)
            if stage_now in {"WALK_FORWARD", "OUT_OF_SAMPLE", "EVALUATION"}:
                if not m.get("walk_forward_passed") and stage_now in {"WALK_FORWARD", "OUT_OF_SAMPLE", "EVALUATION"}:
                    if stage_now != "WALK_FORWARD" and not m.get("walk_forward_passed"):
                        r = self.experiments.advance(eid, passed=False, metrics={**m, "fail_reason": "WALK_FORWARD_REQUIRED"})
                        history.append(r.get("experiment") or {})
                        break
                if stage_now in {"OUT_OF_SAMPLE", "EVALUATION"} and not m.get("calibration_ok"):
                    r = self.experiments.advance(eid, passed=False, metrics={**m, "fail_reason": "CALIBRATION_REQUIRED"})
                    history.append(r.get("experiment") or {})
                    break

            if m.get("overfit_risk", 0) >= 0.7 and stage_hint in {"OUT_OF_SAMPLE", "EVALUATION"}:
                r = self.experiments.advance(eid, passed=False, metrics={**m, "fail_reason": "OVERFIT_RISK"})
                history.append(r.get("experiment") or {})
                break

            r = self.experiments.advance(eid, passed=True, metrics=m)
            history.append(r.get("experiment") or {})
            if not r.get("ok"):
                break
            if (r.get("experiment") or {}).get("status") in {"BLOCKED", "FAILED", "AWAITING_HUMAN"}:
                break

        final = history[-1] if history else current[0]
        return {
            "ok": True,
            "experiment": final,
            "history": history,
            "pipeline": list(PIPELINE),
            "production_affected": False,
        }

    def _overfit_score(self, metrics: dict[str, Any]) -> float:
        bt = float(metrics.get("backtest_sharpe") or metrics.get("train_sharpe") or 0)
        oos = float(metrics.get("oos_sharpe") or metrics.get("sharpe") or 0)
        params = int(metrics.get("n_parameters") or 0)
        score = 0.0
        if bt > 0 and oos > 0 and bt - oos >= 1.0:
            score += 0.45
        if params >= 15:
            score += 0.25
        if metrics.get("excellent_backtest_poor_oos"):
            score += 0.4
        return min(1.0, score)

    def promotion_score(self, metrics: dict[str, Any]) -> dict[str, Any]:
        n = int(metrics.get("sample_size") or 0)
        oos = float(metrics.get("oos_sharpe") or 0)
        cal = 1.0 if metrics.get("calibration_ok") else 0.0
        stab = float(metrics.get("stability") or 0.5)
        dd = float(metrics.get("max_drawdown_pct") or 50)
        rar = float(metrics.get("risk_adjusted_return") or oos)
        regime_ok = 1.0 if metrics.get("regime_robust") else 0.4
        # Safety regression
        blockers: list[str] = []
        if n < 30:
            blockers.append("INSUFFICIENT_SAMPLE")
        if metrics.get("overfit_risk", 0) >= 0.7:
            blockers.append("OVERFIT_RISK")
        if dd > 25:
            blockers.append("DRAWDOWN_TOO_HIGH")
        if metrics.get("risk_increased") or metrics.get("execution_errors_up"):
            blockers.append("SAFETY_REGRESSION")
        if not metrics.get("walk_forward_passed"):
            blockers.append("WALK_FORWARD_REQUIRED")

        raw = (
            min(1.0, n / 100) * 20
            + min(2.0, max(0.0, oos)) / 2 * 20
            + cal * 15
            + stab * 15
            + max(0.0, 1.0 - dd / 50) * 10
            + min(1.0, max(0.0, rar)) * 10
            + regime_ok * 10
        )
        return {
            "promotion_score": round(raw, 1),
            "eligible_candidate": not blockers and raw >= 55,
            "blockers": blockers,
            "note": "Score proposes only — HUMAN_APPROVAL required; no auto champion swap",
        }
