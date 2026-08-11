"""Phase 6 — MemoryEngine: regime/pattern memory + retrieval (similarity ≠ certainty)."""

from __future__ import annotations

import json
import math
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.store import Level7Store


def _vec_from_row(row: dict[str, Any]) -> list[float]:
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
    return [
        float(scores.get("technical") or scores.get("momentum") or 0) / 100.0,
        float(scores.get("volume") or 0) / 100.0,
        float(scores.get("liquidity") or 50) / 100.0,
        float(opp.get("expected_value") or 0) / 5.0,
        float(opp.get("risk_reward") or 1) / 5.0,
        float(row.get("ai_confidence") or 50) / 100.0,
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class MemoryEngine:
    agent_id = "MemoryEngine"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()

    def remember_pattern(
        self,
        *,
        row: dict[str, Any],
        regime: str | None,
        timeframe: str | None = None,
        outcome: str | None = None,
        sample_size: int = 1,
    ) -> dict:
        vec = _vec_from_row(row)
        pid = f"PM-{uuid4().hex[:10]}"
        rec = {
            "id": pid,
            "feature_vector_json": json.dumps(vec),
            "market_regime": str(regime or row.get("regime") or "UNKNOWN"),
            "timeframe": timeframe or "1h",
            "symbol": str(row.get("symbol") or ""),
            "outcome": outcome or "UNKNOWN",
            "sample_size": int(sample_size),
            "created_at": utc_now().isoformat(),
        }
        self.store.upsert_row("pattern_memory", rec)
        self.store.audit(agent=self.agent_id, action="REMEMBER", reason=rec["symbol"], output_data={"id": pid})
        return rec

    def retrieve_similar(
        self,
        row: dict[str, Any],
        *,
        regime: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        target = _vec_from_row(row)
        regime = str(regime or row.get("regime") or "")
        # Prefer same regime; fall back to all
        rows = self.store.list_rows("pattern_memory", where="market_regime=?", params=(regime,), limit=200)
        if not rows:
            rows = self.store.list_rows("pattern_memory", limit=200)

        scored: list[dict[str, Any]] = []
        for r in rows:
            try:
                vec = json.loads(r.get("feature_vector_json") or "[]")
            except json.JSONDecodeError:
                continue
            sim = _cosine(target, vec)
            scored.append({**r, "similarity": round(sim, 4)})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        top = scored[:top_k]
        n = len(top)
        # Sample-size protection
        total_n = sum(int(x.get("sample_size") or 1) for x in top)
        memory_confidence = 0.0
        if total_n >= 50:
            memory_confidence = 0.7
        elif total_n >= 20:
            memory_confidence = 0.45
        elif total_n >= 5:
            memory_confidence = 0.2
        else:
            memory_confidence = 0.05

        wins = sum(1 for x in top if str(x.get("outcome") or "").upper() in {"WIN", "SUCCESS", "CORRECT"})
        return {
            "similar_cases": top,
            "n_cases": n,
            "aggregate_sample_size": total_n,
            "memory_confidence": memory_confidence,
            "naive_win_rate": (wins / n) if n else None,
            "note": "similarity ≠ certainty; small N must not claim 95% success",
            "similarity_is_not_prediction": True,
        }

    def journal_entry(self, entry: dict[str, Any]) -> dict:
        from uuid import uuid4

        rec = {
            "id": entry.get("id") or f"JN-{uuid4().hex[:10]}",
            "symbol": entry.get("symbol"),
            "setup": entry.get("setup"),
            "reason": entry.get("reason"),
            "entry": entry.get("entry"),
            "stop": entry.get("stop"),
            "target": entry.get("target"),
            "thesis": entry.get("thesis"),
            "decision": entry.get("decision"),
            "outcome": entry.get("outcome"),
            "lesson": entry.get("lesson"),
            "created_at": utc_now().isoformat(),
        }
        self.store.upsert_row("journal", rec)
        return rec

    def list_journal(self, limit: int = 30) -> list[dict]:
        return self.store.list_rows("journal", limit=limit)

    def list_patterns(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("pattern_memory", limit=limit)
