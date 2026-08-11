"""Phase 8–9 — StrategyLab + Champion/Challenger (human approval for promotion)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level7.store import Level7Store


class StrategyLab:
    agent_id = "StrategyLab"

    def __init__(self, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()
        self._ensure_champion()

    def _ensure_champion(self) -> None:
        rows = self.store.list_rows("strategies", where="role=?", params=("CHAMPION",), limit=1)
        if rows:
            return
        now = utc_now().isoformat()
        rec = {
            "id": "ST-heuristic-v1",
            "name": "HeuristicEnsemble",
            "version": "v1",
            "status": "PAPER",
            "role": "CHAMPION",
            "regime": "ALL",
            "timeframe": "multi",
            "params_json": json.dumps({"type": "heuristic"}),
            "performance_json": json.dumps({"type": "HEURISTIC", "ml": False}),
            "created_at": now,
            "updated_at": now,
            "note": "Default champion = existing heuristic — not calibrated ML",
        }
        self.store.upsert_row("strategies", rec)

    def list_strategies(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("strategies", limit=limit)

    def create_variant(
        self,
        *,
        base_name: str,
        version: str,
        params: dict | None = None,
        regime: str | None = None,
        timeframe: str | None = None,
    ) -> dict:
        now = utc_now().isoformat()
        rec = {
            "id": f"ST-{uuid4().hex[:10]}",
            "name": base_name,
            "version": version,
            "status": "CREATED",
            "role": "CHALLENGER",
            "regime": regime or "ALL",
            "timeframe": timeframe or "multi",
            "params_json": json.dumps(params or {}),
            "performance_json": json.dumps({}),
            "created_at": now,
            "updated_at": now,
            "note": "Challenger — shadow/paper only until human approval",
        }
        self.store.upsert_row("strategies", rec)
        self.store.audit(agent=self.agent_id, action="CREATE_VARIANT", reason=f"{base_name}:{version}", output_data={"id": rec["id"]})
        return rec

    def update_performance(self, strategy_id: str, performance: dict[str, Any]) -> dict:
        rows = self.store.list_rows("strategies", where="id=?", params=(strategy_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        row["performance_json"] = json.dumps(performance)
        row["updated_at"] = utc_now().isoformat()
        # Drift detection
        hist = float(performance.get("historical_win_rate") or 0)
        recent = float(performance.get("recent_win_rate") or 0)
        if hist and recent and hist - recent >= 0.2:
            performance["strategy_drift"] = True
            performance["drift_alert"] = "STRATEGY_DRIFT"
            row["performance_json"] = json.dumps(performance)
            row["status"] = "CAUTION"
        self.store.upsert_row("strategies", row)
        return {"ok": True, "strategy": row}


class ChampionChallenger:
    agent_id = "ChampionChallenger"

    def __init__(self, lab: StrategyLab | None = None, store: Level7Store | None = None) -> None:
        self.store = store or Level7Store()
        self.lab = lab or StrategyLab(self.store)

    def status(self) -> dict[str, Any]:
        champs = self.store.list_rows("strategies", where="role=?", params=("CHAMPION",), limit=5)
        chall = self.store.list_rows("strategies", where="role=?", params=("CHALLENGER",), limit=20)
        return {
            "champion": champs[0] if champs else None,
            "challengers": chall,
            "note": "Challengers race in paper/shadow only. No auto production promote.",
        }

    def propose_promotion(self, challenger_id: str, *, metrics: dict[str, Any]) -> dict:
        """Returns PROMOTION_CANDIDATE proposal — never applies without human approval."""
        rows = self.store.list_rows("strategies", where="id=?", params=(challenger_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        n = int(metrics.get("sample_size") or 0)
        oos = float(metrics.get("oos_sharpe") or metrics.get("sharpe") or 0)
        dd = float(metrics.get("max_drawdown_pct") or 100)
        champ_sharpe = 0.0
        champs = self.store.list_rows("strategies", where="role=?", params=("CHAMPION",), limit=1)
        if champs:
            try:
                perf = json.loads(champs[0].get("performance_json") or "{}")
                champ_sharpe = float(perf.get("sharpe") or 0)
            except (TypeError, ValueError, json.JSONDecodeError):
                champ_sharpe = 0.0

        blockers: list[str] = []
        if n < 30:
            blockers.append("INSUFFICIENT_SAMPLE")
        if oos < champ_sharpe and champ_sharpe > 0:
            blockers.append("PERFORMANCE_REGRESSION")
        if dd > 25:
            blockers.append("DRAWDOWN_TOO_HIGH")
        if not metrics.get("walk_forward_passed"):
            blockers.append("WALK_FORWARD_REQUIRED")
        if not metrics.get("calibration_ok"):
            blockers.append("CALIBRATION_REQUIRED")

        if blockers:
            self.store.audit(
                agent=self.agent_id,
                action="PROMOTION_BLOCKED",
                reason=",".join(blockers),
                output_data={"id": challenger_id},
            )
            return {"ok": False, "reason": "PROMOTION_BLOCKED", "blockers": blockers}

        row["status"] = "PROMOTION_CANDIDATE"
        row["updated_at"] = utc_now().isoformat()
        row["performance_json"] = json.dumps(metrics)
        self.store.upsert_row("strategies", row)
        self.store.audit(
            agent=self.agent_id,
            action="PROMOTION_CANDIDATE",
            reason="awaiting_human",
            output_data={"id": challenger_id},
        )
        return {
            "ok": True,
            "status": "PROMOTION_CANDIDATE",
            "strategy": row,
            "requires": "HUMAN_APPROVAL",
            "note": "AI cannot promote itself to production champion",
        }

    def human_approve_promotion(self, challenger_id: str, *, approved_by: str) -> dict:
        """Only human-triggered. Demotes previous champion to ARCHIVED role Challenger history."""
        rows = self.store.list_rows("strategies", where="id=?", params=(challenger_id,), limit=1)
        if not rows:
            return {"ok": False, "reason": "not_found"}
        row = rows[0]
        if row.get("status") != "PROMOTION_CANDIDATE":
            return {"ok": False, "reason": "not_promotion_candidate"}
        # Demote existing champions
        for c in self.store.list_rows("strategies", where="role=?", params=("CHAMPION",), limit=20):
            c["role"] = "FORMER_CHAMPION"
            c["status"] = "ARCHIVED"
            c["updated_at"] = utc_now().isoformat()
            self.store.upsert_row("strategies", c)
        row["role"] = "CHAMPION"
        row["status"] = "PAPER"  # still not LIVE unlock
        row["updated_at"] = utc_now().isoformat()
        row["note"] = f"Promoted by {approved_by} — paper/shadow scoring default, not live broker unlock"
        self.store.upsert_row("strategies", row)
        self.store.audit(
            agent=self.agent_id,
            action="HUMAN_PROMOTE",
            reason=approved_by,
            output_data={"id": challenger_id},
        )
        return {"ok": True, "champion": row, "live_broker_unlocked": False}
