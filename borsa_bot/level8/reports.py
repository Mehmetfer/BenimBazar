"""Research budget + periodic learning reports."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level8.store import Level8Store


class ResearchBudget:
    agent_id = "ResearchBudget"

    def __init__(
        self,
        store: Level8Store | None = None,
        *,
        max_experiments: int = 20,
        max_api_calls: int = 400,
        max_model_calls: int = 100,
    ) -> None:
        self.store = store or Level8Store()
        self.max_experiments = max_experiments
        self.max_api_calls = max_api_calls
        self.max_model_calls = max_model_calls

    def _day(self) -> str:
        return utc_now().strftime("%Y-%m-%d")

    def _row(self) -> dict:
        day = self._day()
        row = self.store.get("research_budget", "day_key", day)
        if row:
            return row
        row = {
            "day_key": day,
            "experiments": 0,
            "api_calls": 0,
            "model_calls": 0,
            "max_experiments": self.max_experiments,
            "max_api_calls": self.max_api_calls,
            "max_model_calls": self.max_model_calls,
        }
        self.store.upsert("research_budget", row, pk="day_key")
        return row

    def allow(self, *, experiments: int = 0, api_calls: int = 0, model_calls: int = 0) -> dict[str, Any]:
        row = self._row()
        if int(row["experiments"]) + experiments > int(row["max_experiments"]):
            return {"allowed": False, "reason": "MAX_EXPERIMENTS"}
        if int(row["api_calls"]) + api_calls > int(row["max_api_calls"]):
            return {"allowed": False, "reason": "MAX_API_CALLS"}
        if int(row["model_calls"]) + model_calls > int(row["max_model_calls"]):
            return {"allowed": False, "reason": "MAX_MODEL_CALLS"}
        row["experiments"] = int(row["experiments"]) + experiments
        row["api_calls"] = int(row["api_calls"]) + api_calls
        row["model_calls"] = int(row["model_calls"]) + model_calls
        self.store.upsert("research_budget", row, pk="day_key")
        return {"allowed": True, "budget": row}


class LearningReports:
    agent_id = "LearningReports"

    def __init__(self, store: Level8Store | None = None) -> None:
        self.store = store or Level8Store()

    def hourly(self, metrics: dict[str, Any]) -> dict:
        return self._save("HOURLY", {
            "data_quality": metrics.get("data_quality"),
            "signal_quality": metrics.get("signal_quality"),
            "prediction_accuracy": metrics.get("prediction_accuracy"),
            "false_positives": metrics.get("false_positives"),
            "false_negatives": metrics.get("false_negatives"),
            "market_regime": metrics.get("market_regime"),
            "open_positions": metrics.get("open_positions"),
            "risk": metrics.get("risk"),
            "note": "Hourly observation — not a live unlock",
        })

    def daily(self, metrics: dict[str, Any]) -> dict:
        return self._save("DAILY", {
            "signals": metrics.get("signals"),
            "predictions": metrics.get("predictions"),
            "trades": metrics.get("trades"),
            "model_performance": metrics.get("model_performance"),
            "strategy_performance": metrics.get("strategy_performance"),
            "regime_performance": metrics.get("regime_performance"),
            "symbol_performance": metrics.get("symbol_performance"),
            "timeframe_performance": metrics.get("timeframe_performance"),
        })

    def weekly(self, answers: dict[str, Any]) -> dict:
        content = {
            "what_worked": answers.get("what_worked"),
            "what_failed": answers.get("what_failed"),
            "why_failed": answers.get("why_failed"),
            "best_setup": answers.get("best_setup"),
            "deteriorated": answers.get("deteriorated"),
            "valuable_indicators": answers.get("valuable_indicators"),
            "noisy_indicators": answers.get("noisy_indicators"),
            "regime_changes": answers.get("regime_changes"),
            "degrading_model": answers.get("degrading_model"),
            "test_next": answers.get("test_next"),
            "correlation_not_causation": True,
        }
        return self._save("WEEKLY", content)

    def monthly(self, audit: dict[str, Any]) -> dict:
        return self._save("MONTHLY", {
            "model_performance": audit.get("model_performance"),
            "strategy_performance": audit.get("strategy_performance"),
            "calibration": audit.get("calibration"),
            "drift": audit.get("drift"),
            "drawdown": audit.get("drawdown"),
            "false_signals": audit.get("false_signals"),
            "risk_adjusted_return": audit.get("risk_adjusted_return"),
            "guaranteed_profit": False,
        })

    def autonomous_research_report(self, bundle: dict[str, Any]) -> dict:
        return self._save("AUTONOMOUS", {
            "what_changed": bundle.get("what_changed"),
            "what_learned": bundle.get("what_learned"),
            "what_failed": bundle.get("what_failed"),
            "what_succeeded": bundle.get("what_succeeded"),
            "hypotheses_pending": bundle.get("hypotheses_pending"),
            "experiments_running": bundle.get("experiments_running"),
            "promote": bundle.get("promote"),
            "reject": bundle.get("reject"),
            "no_fake_improvement": True,
        })

    def _save(self, period: str, content: dict[str, Any]) -> dict:
        rec = {
            "id": f"RP-{uuid4().hex[:10]}",
            "period": period,
            "content_json": json.dumps(content),
            "created_at": utc_now().isoformat(),
        }
        self.store.upsert("learning_reports", rec)
        return rec

    def list_reports(self, period: str | None = None, limit: int = 20) -> list[dict]:
        if period:
            return self.store.list_rows("learning_reports", where="period=?", params=(period,), limit=limit)
        return self.store.list_rows("learning_reports", limit=limit)
