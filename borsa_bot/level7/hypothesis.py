"""Phase 3 — HypothesisEngine: create/lifecycle hypotheses (never auto-apply to production)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.store import Level7Store

HYPOTHESIS_STATES = (
    "CREATED",
    "BACKTESTING",
    "VALIDATING",
    "PAPER",
    "SHADOW",
    "PROMOTION_CANDIDATE",
    "REJECTED",
    "ARCHIVED",
)

_ALLOWED_TRANSITIONS = {
    "CREATED": {"BACKTESTING", "REJECTED", "ARCHIVED"},
    "BACKTESTING": {"VALIDATING", "REJECTED", "ARCHIVED"},
    "VALIDATING": {"PAPER", "REJECTED", "ARCHIVED"},
    "PAPER": {"SHADOW", "REJECTED", "ARCHIVED"},
    "SHADOW": {"PROMOTION_CANDIDATE", "REJECTED", "ARCHIVED"},
    "PROMOTION_CANDIDATE": {"ARCHIVED", "REJECTED"},  # human approval external
    "REJECTED": {"ARCHIVED"},
    "ARCHIVED": set(),
}


@dataclass
class Hypothesis:
    id: str
    title: str
    statement: str
    status: str
    regime: str | None = None
    timeframe: str | None = None
    params_json: str = "{}"
    metrics_json: str = "{}"
    created_at: str = ""
    updated_at: str = ""
    note: str = "Hypothesis cannot modify production strategy without human approval"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HypothesisEngine:
    agent_id = "HypothesisEngine"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()

    def seed_from_research(self, questions: list[dict[str, Any]] | None = None) -> list[Hypothesis]:
        """Generate starter hypotheses from research themes (deterministic templates)."""
        created: list[Hypothesis] = []
        templates = [
            ("H-VOL-EMA", "High volume + EMA alignment improves breakout quality", "BULL", "1h"),
            ("H-LOWVOL-BO", "Breakouts during low volatility have higher failure probability", "SIDEWAYS", "15m"),
            ("H-MTF-15-1H", "15m signals perform better when 1h trend agrees", "BULL", "15m+1h"),
        ]
        for title, statement, regime, tf in templates:
            # skip if similar title exists
            existing = self.store.list_rows("hypotheses", where="title=?", params=(title,), limit=1)
            if existing:
                continue
            h = self.create(title=title, statement=statement, regime=regime, timeframe=tf)
            created.append(h)
        if questions:
            for q in questions[:2]:
                h = self.create(
                    title=f"H-FROM-{q.get('id', 'RQ')}",
                    statement=str(q.get("question") or "")[:240],
                    regime=None,
                    timeframe=None,
                )
                created.append(h)
        return created

    def create(
        self,
        *,
        title: str,
        statement: str,
        regime: str | None = None,
        timeframe: str | None = None,
        params: dict | None = None,
    ) -> Hypothesis:
        import json

        now = utc_now().isoformat()
        h = Hypothesis(
            id=f"HY-{uuid4().hex[:10]}",
            title=title,
            statement=statement,
            status="CREATED",
            regime=regime,
            timeframe=timeframe,
            params_json=json.dumps(params or {}),
            created_at=now,
            updated_at=now,
        )
        self.store.upsert_row("hypotheses", h.to_dict())
        self.store.audit(agent=self.agent_id, action="CREATE", reason=title, output_data={"id": h.id})
        return h

    def transition(self, hypothesis_id: str, new_status: str, *, metrics: dict | None = None) -> dict:
        import json

        rows = self.store.list_rows("hypotheses", where="id=?", params=(hypothesis_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        cur = row["status"]
        allowed = _ALLOWED_TRANSITIONS.get(cur, set())
        if new_status not in allowed:
            return {"ok": False, "reason": f"illegal_transition_{cur}_to_{new_status}"}
        row["status"] = new_status
        row["updated_at"] = utc_now().isoformat()
        if metrics:
            row["metrics_json"] = json.dumps(metrics)
        self.store.upsert_row("hypotheses", row)
        self.store.audit(
            agent=self.agent_id,
            action="TRANSITION",
            reason=f"{cur}->{new_status}",
            output_data={"id": hypothesis_id, "status": new_status},
        )
        return {"ok": True, "hypothesis": row}

    def list_hypotheses(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("hypotheses", limit=limit)
