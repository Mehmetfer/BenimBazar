"""Phase 7 — OutcomeAnalyzer + RootCauseEngine (decision/prediction feedback)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from level7.store import Level7Store

ERROR_TAXONOMY = (
    "DATA_ERROR",
    "REGIME_ERROR",
    "MODEL_ERROR",
    "ENTRY_ERROR",
    "STOP_ERROR",
    "TARGET_ERROR",
    "LIQUIDITY_ERROR",
    "EXECUTION_ERROR",
    "WRONG_DIRECTION",
    "FALSE_BREAKOUT",
    "BAD_REGIME",
    "UNKNOWN",
)


@dataclass
class OutcomeReport:
    predicted_direction: str | None
    actual_direction: str | None
    predicted_return: float | None
    actual_return: float | None
    direction_correct: bool | None
    absolute_error: float | None
    error_class: str
    root_cause: str
    lesson: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OutcomeAnalyzer:
    agent_id = "OutcomeAnalyzer"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()

    def compare(
        self,
        *,
        predicted_direction: str | None,
        actual_direction: str | None = None,
        predicted_return: float | None = None,
        actual_return: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> OutcomeReport:
        ctx = context or {}
        direction_correct = None
        if predicted_direction and actual_direction:
            pd = predicted_direction.upper()
            ad = actual_direction.upper()
            bull = {"BUY", "STRONG_BUY", "AL", "UP", "BULL"}
            bear = {"SELL", "STRONG_SELL", "SAT", "DOWN", "BEAR"}
            if (pd in bull and ad in bull) or (pd in bear and ad in bear) or pd == ad:
                direction_correct = True
            else:
                direction_correct = False

        abs_err = None
        if predicted_return is not None and actual_return is not None:
            abs_err = abs(float(predicted_return) - float(actual_return))

        error_class = "UNKNOWN"
        root = "Insufficient outcome data"
        lesson = "Keep measuring — do not claim certainty"

        if direction_correct is False:
            if ctx.get("data_conflict") or ctx.get("mtf_conflict"):
                error_class = "MODEL_ERROR"
                root = "Timeframe conflict ignored or underweighted"
                lesson = "Raise MTF conflict → WAIT / haircut confidence"
            elif ctx.get("volume_weak"):
                error_class = "FALSE_BREAKOUT"
                root = "Breakout failed because volume confirmation was insufficient"
                lesson = "Require volume confirmation for breakout entries"
            elif str(ctx.get("regime") or "").upper() in {"BEAR", "STRONG_BEAR"} and str(predicted_direction or "").upper() in {
                "BUY",
                "STRONG_BUY",
                "AL",
            }:
                error_class = "REGIME_ERROR"
                root = "Long bias against bearish regime"
                lesson = "Align direction with regime or NO_TRADE"
            elif ctx.get("low_liquidity"):
                error_class = "LIQUIDITY_ERROR"
                root = "Edge eroded by liquidity/spread"
                lesson = "Hard-filter low liquidity before proposals"
            else:
                error_class = "WRONG_DIRECTION"
                root = "Directional thesis invalidated by price path"
                lesson = "Review thesis invalidation rules"
        elif direction_correct is True:
            error_class = "UNKNOWN"
            root = "Direction matched — still review RR and execution quality"
            lesson = "Winning direction ≠ optimal entry/exit"

        if ctx.get("data_stale") or ctx.get("data_invalid"):
            error_class = "DATA_ERROR"
            root = "Decision used stale/invalid data"
            lesson = "Fail-closed: NO_TRADE on bad data"

        report = OutcomeReport(
            predicted_direction=predicted_direction,
            actual_direction=actual_direction,
            predicted_return=predicted_return,
            actual_return=actual_return,
            direction_correct=direction_correct,
            absolute_error=abs_err,
            error_class=error_class,
            root_cause=root,
            lesson=lesson,
            notes=["confidence ≠ calibrated probability"],
        )
        self.store.audit(
            agent=self.agent_id,
            action="COMPARE",
            reason=error_class,
            output_data=report.to_dict(),
        )
        return report

    def self_evaluate_recent(self, decisions: list[dict[str, Any]], *, window: int = 20) -> dict[str, Any]:
        chunk = decisions[:window]
        n = len(chunk)
        with_outcome = [d for d in chunk if d.get("outcome") or d.get("direction_correct") is not None]
        correct = sum(
            1
            for d in with_outcome
            if d.get("direction_correct") is True or str(d.get("outcome") or "").upper() in {"WIN", "CORRECT"}
        )
        rate = (correct / len(with_outcome)) if with_outcome else None
        return {
            "window": window,
            "n_decisions": n,
            "n_with_outcome": len(with_outcome),
            "direction_accuracy": rate,
            "sample_sufficient": len(with_outcome) >= 30,
            "note": "Small windows must not declare model superiority",
        }


class RootCauseEngine:
    agent_id = "RootCauseEngine"

    def explain(self, outcome: OutcomeReport | dict[str, Any]) -> dict[str, Any]:
        if isinstance(outcome, OutcomeReport):
            o = outcome.to_dict()
        else:
            o = outcome
        return {
            "why": o.get("root_cause"),
            "error_class": o.get("error_class"),
            "lesson": o.get("lesson"),
            "taxonomy": list(ERROR_TAXONOMY),
            "note": "Root cause is structured heuristic — not omniscience",
        }
