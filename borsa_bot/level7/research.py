"""Phase 2 — ResearchAgent: generate & store research questions (no production mutation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.store import Level7Store


@dataclass
class ResearchQuestion:
    id: str
    question: str
    reason: str
    priority: str  # LOW | MEDIUM | HIGH
    dataset: str
    status: str  # OPEN | IN_PROGRESS | ANSWERED | ARCHIVED
    result: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchAgent:
    agent_id = "ResearchAgent"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()

    def propose_from_context(
        self,
        *,
        regime: dict[str, Any] | None = None,
        learning: dict[str, Any] | None = None,
        debate_stats: dict[str, Any] | None = None,
    ) -> list[ResearchQuestion]:
        regime = regime or {}
        learning = learning or {}
        debate_stats = debate_stats or {}
        qs: list[ResearchQuestion] = []
        primary = str(regime.get("primary") or "UNKNOWN")

        qs.append(
            self._q(
                f"Does volume confirmation still improve breakout quality in {primary} regime?",
                reason="Regime-specific filter value",
                priority="HIGH",
                dataset=f"regime={primary},feature=volume",
            )
        )
        qs.append(
            self._q(
                "Which timeframe (15m/1h/1d) has the strongest directional accuracy recently?",
                reason="MTF predictive strength audit",
                priority="HIGH",
                dataset="mtf_horizons",
            )
        )
        if float(learning.get("sample_size") or 0) < 30:
            qs.append(
                self._q(
                    "Is current sample size sufficient for calibrated probability claims?",
                    reason="Calibration / sample-size protection",
                    priority="HIGH",
                    dataset="prediction_history",
                )
            )
        if debate_stats.get("conflict_rate", 0) and float(debate_stats["conflict_rate"]) > 0.3:
            qs.append(
                self._q(
                    "Why are MTF conflicts rising and do they predict false breakouts?",
                    reason="Model disagreement / conflict analysis",
                    priority="MEDIUM",
                    dataset="debate_conflicts",
                )
            )
        qs.append(
            self._q(
                "Is RSI adding incremental information beyond momentum/trend_momentum bucket?",
                reason="Feature redundancy / anti double-count",
                priority="LOW",
                dataset="feature_ablation",
            )
        )

        for q in qs:
            self.store.upsert_row("research_questions", q.to_dict())
            self.store.audit(agent=self.agent_id, action="CREATE_QUESTION", reason=q.reason, output_data={"id": q.id})
        return qs

    def list_questions(self, limit: int = 30) -> list[dict]:
        return self.store.list_rows("research_questions", limit=limit)

    def answer(self, question_id: str, result: str) -> dict:
        rows = self.store.list_rows("research_questions", where="id=?", params=(question_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        row["status"] = "ANSWERED"
        row["result"] = result
        row["updated_at"] = utc_now().isoformat()
        self.store.upsert_row("research_questions", row)
        self.store.audit(agent=self.agent_id, action="ANSWER", reason=question_id, output_data={"result": result[:200]})
        return {"ok": True, "question": row}

    def _q(self, question: str, *, reason: str, priority: str, dataset: str) -> ResearchQuestion:
        now = utc_now().isoformat()
        return ResearchQuestion(
            id=f"RQ-{uuid4().hex[:10]}",
            question=question,
            reason=reason,
            priority=priority,
            dataset=dataset,
            status="OPEN",
            created_at=now,
            updated_at=now,
        )
