"""Drift detection + automatic de-rating (never raises risk limits)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from config.models import utc_now
from level8.store import Level8Store


class DriftDetector:
    agent_id = "DriftDetector"

    def __init__(self, store: Level8Store | None = None) -> None:
        self.store = store or Level8Store()

    def record(self, drift_type: str, *, severity: str = "MEDIUM", detail: dict | None = None) -> dict:
        rec = {
            "id": f"DR-{uuid4().hex[:10]}",
            "drift_type": drift_type.upper(),
            "severity": severity.upper(),
            "detail_json": json.dumps(detail or {}),
            "created_at": utc_now().isoformat(),
            "status": "OPEN",
        }
        self.store.upsert("drift_events", rec)
        self.store.audit(agent=self.agent_id, action="DRIFT", reason=drift_type, payload=detail)
        return rec

    def detect_from_metrics(
        self,
        *,
        feature_shift: float | None = None,
        concept_shift: float | None = None,
        historical_win_rate: float | None = None,
        recent_win_rate: float | None = None,
    ) -> list[dict]:
        events: list[dict] = []
        if feature_shift is not None and feature_shift >= 0.25:
            events.append(self.record("DATA_DRIFT", severity="HIGH" if feature_shift >= 0.4 else "MEDIUM", detail={"feature_shift": feature_shift}))
        if concept_shift is not None and concept_shift >= 0.2:
            events.append(self.record("CONCEPT_DRIFT", severity="HIGH" if concept_shift >= 0.35 else "MEDIUM", detail={"concept_shift": concept_shift}))
        if historical_win_rate is not None and recent_win_rate is not None:
            drop = float(historical_win_rate) - float(recent_win_rate)
            if drop >= 0.2:
                events.append(
                    self.record(
                        "STRATEGY_DRIFT",
                        severity="HIGH" if drop >= 0.3 else "MEDIUM",
                        detail={"historical_win_rate": historical_win_rate, "recent_win_rate": recent_win_rate, "drop": drop},
                    )
                )
        return events

    def derate(self, *, open_drifts: list[dict] | None = None) -> dict[str, Any]:
        """Confidence/size haircut only — NEVER increases risk limits."""
        open_drifts = open_drifts or self.store.list_rows("drift_events", where="status=?", params=("OPEN",), limit=50)
        conf_mult = 1.0
        size_mult = 1.0
        priority_mult = 1.0
        reasons: list[str] = []
        for d in open_drifts:
            t = str(d.get("drift_type") or "")
            sev = str(d.get("severity") or "MEDIUM")
            hit = 0.15 if sev == "MEDIUM" else 0.3
            conf_mult = min(conf_mult, 1.0 - hit)
            size_mult = min(size_mult, 1.0 - hit)
            priority_mult = min(priority_mult, 1.0 - hit * 0.5)
            reasons.append(t)
        return {
            "confidence_mult": round(conf_mult, 3),
            "size_mult": round(size_mult, 3),
            "signal_priority_mult": round(priority_mult, 3),
            "risk_limits_increased": False,
            "reasons": reasons or ["none"],
            "note": "De-rate only; AI cannot raise risk limits or disable kill switch",
        }

    def list_open(self, limit: int = 50) -> list[dict]:
        return self.store.list_rows("drift_events", where="status=?", params=("OPEN",), limit=limit)
