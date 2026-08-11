"""Decision snapshots + look-ahead-safe replay."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level8.store import Level8Store


class DecisionSnapshotService:
    agent_id = "DecisionSnapshotService"

    def __init__(self, store: Level8Store | None = None) -> None:
        self.store = store or Level8Store()

    def capture(
        self,
        *,
        decision_id: str | None = None,
        symbol: str,
        market_type: str = "BIST",
        signal: str,
        confidence: float | None = None,
        uncertainty: str = "UNKNOWN",
        expected_value: float | None = None,
        entry: float | None = None,
        stop: float | None = None,
        target: float | None = None,
        regime: str | None = None,
        timeframe: str = "15m",
        features: dict | None = None,
        indicators: dict | None = None,
        model: str = "heuristic_ensemble",
        prompt_version: str = "trading_reasoning_v1",
        strategy_version: str = "HeuristicEnsemble:v1",
        data_kind: str = "UNKNOWN",
        provider: str = "",
        data_timestamp: str | None = None,
        market_snapshot: dict | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        # Production learning must not ingest MOCK
        kind = str(data_kind or "UNKNOWN").upper()
        if kind in {"MOCK", "TEST"}:
            self.store.audit(
                agent=self.agent_id,
                action="SNAPSHOT_REJECTED",
                reason="MOCK_TEST_NOT_FOR_PRODUCTION_LEARNING",
                payload={"symbol": symbol, "data_kind": kind},
                result="REJECTED",
            )
            return {"ok": False, "reason": "MOCK_TEST_NOT_FOR_PRODUCTION_LEARNING", "data_kind": kind}

        ts = timestamp or utc_now().isoformat()
        did = decision_id or f"DS-{uuid4().hex[:12]}"
        row = {
            "decision_id": did,
            "symbol": symbol,
            "market_type": market_type.upper(),
            "timestamp": ts,
            "market_regime": regime,
            "timeframe": timeframe,
            "features_json": json.dumps(features or {}),
            "indicators_json": json.dumps(indicators or {}),
            "model": model,
            "prompt_version": prompt_version,
            "strategy_version": strategy_version,
            "confidence": confidence,
            "uncertainty": uncertainty,
            "signal": signal,
            "entry": entry,
            "stop": stop,
            "target": target,
            "expected_value": expected_value,
            "data_kind": kind,
            "provider": provider,
            "data_timestamp": data_timestamp or ts,
            "market_snapshot_json": json.dumps(market_snapshot or {}),
            "outcome_json": None,
            "error_class": None,
            "root_cause": None,
            "created_at": utc_now().isoformat(),
        }
        self.store.upsert("decision_snapshots", row, pk="decision_id")
        self.store.audit(agent=self.agent_id, action="CAPTURE", reason=did, payload={"symbol": symbol, "signal": signal})
        return {"ok": True, "snapshot": row}

    def attach_outcome(
        self,
        decision_id: str,
        *,
        outcome: dict[str, Any],
        error_class: str | None = None,
        root_cause: str | None = None,
    ) -> dict:
        row = self.store.get("decision_snapshots", "decision_id", decision_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        # Look-ahead guard: outcome timestamp must be >= decision timestamp (informational)
        out_ts = str(outcome.get("outcome_timestamp") or utc_now().isoformat())
        if out_ts < str(row.get("timestamp") or ""):
            return {"ok": False, "reason": "LOOK_AHEAD_REJECTED", "note": "outcome timestamp before decision"}
        row["outcome_json"] = json.dumps(outcome)
        row["error_class"] = error_class
        row["root_cause"] = root_cause
        self.store.upsert("decision_snapshots", row, pk="decision_id")
        self.store.audit(agent=self.agent_id, action="OUTCOME", reason=decision_id, payload={"error_class": error_class})
        return {"ok": True, "snapshot": row}

    def replay(self, decision_id: str) -> dict[str, Any]:
        """Replay decision state as known at decision_timestamp — no future leakage."""
        row = self.store.get("decision_snapshots", "decision_id", decision_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        decision_ts = str(row.get("timestamp") or "")
        outcome = json.loads(row["outcome_json"]) if row.get("outcome_json") else None
        # Explicitly separate what was known then vs outcome (after)
        return {
            "ok": True,
            "decision_id": decision_id,
            "as_of": decision_ts,
            "known_at_decision": {
                "symbol": row.get("symbol"),
                "market_type": row.get("market_type"),
                "market_regime": row.get("market_regime"),
                "timeframe": row.get("timeframe"),
                "features": json.loads(row.get("features_json") or "{}"),
                "indicators": json.loads(row.get("indicators_json") or "{}"),
                "model": row.get("model"),
                "prompt_version": row.get("prompt_version"),
                "strategy_version": row.get("strategy_version"),
                "confidence": row.get("confidence"),
                "uncertainty": row.get("uncertainty"),
                "signal": row.get("signal"),
                "entry": row.get("entry"),
                "stop": row.get("stop"),
                "target": row.get("target"),
                "expected_value": row.get("expected_value"),
                "data_kind": row.get("data_kind"),
                "provider": row.get("provider"),
                "data_timestamp": row.get("data_timestamp"),
                "market_snapshot": json.loads(row.get("market_snapshot_json") or "{}"),
            },
            "actual_outcome": outcome,  # labeled separately — not an input
            "error_class": row.get("error_class"),
            "root_cause": row.get("root_cause"),
            "look_ahead_protected": True,
            "note": "Replay exposes outcome separately; learning must not feed outcome into input features",
        }

    def list_recent(self, limit: int = 30) -> list[dict]:
        return self.store.list_rows("decision_snapshots", limit=limit, order="timestamp DESC")
