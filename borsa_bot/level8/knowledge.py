"""Research knowledge memory with freshness / decay / invalidation."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level8.store import Level8Store


class KnowledgeMemory:
    agent_id = "KnowledgeMemory"

    def __init__(self, store: Level8Store | None = None) -> None:
        self.store = store or Level8Store()

    def add(
        self,
        *,
        observation: str,
        result: str,
        confidence: float = 0.4,
        hypothesis_id: str | None = None,
        experiment_id: str | None = None,
        evidence: dict | None = None,
    ) -> dict:
        now = utc_now().isoformat()
        rec = {
            "id": f"KM-{uuid4().hex[:10]}",
            "observation": observation,
            "hypothesis_id": hypothesis_id,
            "experiment_id": experiment_id,
            "result": result,
            "confidence": float(confidence),
            "evidence_json": json.dumps(evidence or {}),
            "freshness": "FRESH",
            "last_validated": now,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        }
        self.store.upsert("knowledge_memory", rec)
        self.store.audit(agent=self.agent_id, action="ADD", reason=rec["id"], payload={"observation": observation[:120]})
        return rec

    def mark_stale(self, knowledge_id: str, *, reason: str = "STALE_KNOWLEDGE") -> dict:
        row = self.store.get("knowledge_memory", "id", knowledge_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        row["freshness"] = "STALE"
        row["status"] = "STALE_KNOWLEDGE"
        row["updated_at"] = utc_now().isoformat()
        row["result"] = f"{row.get('result') or ''}|{reason}"
        self.store.upsert("knowledge_memory", row)
        # Do not delete
        return {"ok": True, "knowledge": row, "deleted": False}

    def list_active(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("knowledge_memory", where="status=?", params=("ACTIVE",), limit=limit)

    def list_all(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("knowledge_memory", limit=limit)
