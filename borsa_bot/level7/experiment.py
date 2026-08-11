"""Phase 4 — ExperimentEngine: mandatory validation pipeline (no auto production apply)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.hypothesis import HypothesisEngine
from level7.store import Level7Store

# Mandatory pipeline stages
PIPELINE = (
    "HYPOTHESIS",
    "DATASET",
    "BACKTEST",
    "WALK_FORWARD",
    "OUT_OF_SAMPLE",
    "PAPER",
    "SHADOW",
    "EVALUATION",
    "HUMAN_APPROVAL",
)


@dataclass
class Experiment:
    id: str
    hypothesis_id: str
    stage: str
    status: str  # RUNNING | PASSED | FAILED | BLOCKED | AWAITING_HUMAN
    dataset: str
    metrics_json: str = "{}"
    theoretical: int = 1  # 1 = theoretical (missing fees/slippage realism)
    created_at: str = ""
    updated_at: str = ""
    note: str = "Cannot skip to production. HUMAN_APPROVAL required for promotion."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentEngine:
    agent_id = "ExperimentEngine"

    def __init__(self, store: Level7Store | None = None, hypotheses: HypothesisEngine | None = None) -> None:
        self.store = store or Level7Store()
        self.hypotheses = hypotheses or HypothesisEngine(self.store)

    def start(self, hypothesis_id: str, *, dataset: str = "historical_bars") -> Experiment:
        now = utc_now().isoformat()
        exp = Experiment(
            id=f"EX-{uuid4().hex[:10]}",
            hypothesis_id=hypothesis_id,
            stage="DATASET",
            status="RUNNING",
            dataset=dataset,
            created_at=now,
            updated_at=now,
        )
        self.store.upsert_row("experiments", exp.to_dict())
        self.hypotheses.transition(hypothesis_id, "BACKTESTING")
        self.store.audit(agent=self.agent_id, action="START", reason=hypothesis_id, output_data={"id": exp.id})
        return exp

    def advance(self, experiment_id: str, *, passed: bool, metrics: dict | None = None) -> dict:
        rows = self.store.list_rows("experiments", where="id=?", params=(experiment_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        stage = row["stage"]
        try:
            idx = PIPELINE.index(stage) if stage in PIPELINE else PIPELINE.index("DATASET")
        except ValueError:
            idx = 1

        if not passed:
            row["status"] = "FAILED"
            row["updated_at"] = utc_now().isoformat()
            if metrics:
                row["metrics_json"] = json.dumps(metrics)
            self.store.upsert_row("experiments", row)
            self.hypotheses.transition(row["hypothesis_id"], "REJECTED", metrics=metrics)
            return {"ok": True, "experiment": row, "note": "Failed stage — hypothesis REJECTED"}

        # Sample-size / significance guard
        metrics = metrics or {}
        n = int(metrics.get("sample_size") or metrics.get("n") or 0)
        if stage in {"BACKTEST", "WALK_FORWARD", "OUT_OF_SAMPLE", "EVALUATION"} and n and n < 30:
            metrics["statistical_significance"] = "INSUFFICIENT"
            metrics["winner_declared"] = False
            row["metrics_json"] = json.dumps(metrics)
            row["status"] = "BLOCKED"
            row["updated_at"] = utc_now().isoformat()
            row["note"] = "PROMOTION BLOCKED — sample size too small (N<30)"
            self.store.upsert_row("experiments", row)
            return {"ok": True, "experiment": row, "note": row["note"]}

        next_idx = min(idx + 1, len(PIPELINE) - 1)
        next_stage = PIPELINE[next_idx]
        row["stage"] = next_stage
        row["updated_at"] = utc_now().isoformat()
        if metrics:
            row["metrics_json"] = json.dumps(metrics)

        if next_stage == "HUMAN_APPROVAL":
            row["status"] = "AWAITING_HUMAN"
            self.hypotheses.transition(row["hypothesis_id"], "PROMOTION_CANDIDATE", metrics=metrics)
        elif next_stage == "PAPER":
            row["status"] = "RUNNING"
            self.hypotheses.transition(row["hypothesis_id"], "PAPER", metrics=metrics)
        elif next_stage == "SHADOW":
            row["status"] = "RUNNING"
            self.hypotheses.transition(row["hypothesis_id"], "SHADOW", metrics=metrics)
        elif next_stage in {"BACKTEST", "WALK_FORWARD", "OUT_OF_SAMPLE", "EVALUATION", "DATASET"}:
            row["status"] = "RUNNING"
            if next_stage == "WALK_FORWARD":
                self.hypotheses.transition(row["hypothesis_id"], "VALIDATING", metrics=metrics)
        else:
            row["status"] = "PASSED"

        # Mark theoretical unless fees/slippage present
        if not metrics.get("includes_fees") or not metrics.get("includes_slippage"):
            row["theoretical"] = 1
            row["note"] = "THEORETICAL — fees/slippage incomplete"

        self.store.upsert_row("experiments", row)
        self.store.audit(
            agent=self.agent_id,
            action="ADVANCE",
            reason=f"->{next_stage}",
            output_data={"id": experiment_id, "stage": next_stage, "status": row["status"]},
        )
        return {"ok": True, "experiment": row}

    def list_experiments(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("experiments", limit=limit)
