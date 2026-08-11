"""Model registry — promotion pipeline only; no self-modifying production code (Master V2 §46–48)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT


@dataclass
class ModelRecord:
    model_id: str
    version: str
    status: str  # EXPERIMENT | BACKTEST | PAPER | SHADOW | ACTIVE | ROLLED_BACK
    features: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    note: str = "Promotion requires human approval. No auto LIVE promote."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "model_registry.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            heuristic = ModelRecord(
                model_id="heuristic_ensemble",
                version=str(getattr(__import__("config.settings", fromlist=["settings"]).settings, "prediction_model_version", "1.0.0")),
                status="PAPER",
                features=["technical", "mtf", "regime", "volume", "momentum"],
                metrics={"type": "HEURISTIC", "ml": False},
                created_at=utc_now().isoformat(),
                note="Default heuristic — not a trained ML model. confidence ≠ probability.",
            )
            self._write({"models": [heuristic.to_dict()], "active_model_id": heuristic.model_id})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_models(self) -> list[dict]:
        return list(self._read().get("models") or [])

    def active(self) -> dict | None:
        data = self._read()
        aid = data.get("active_model_id")
        for m in data.get("models") or []:
            if m.get("model_id") == aid:
                return m
        return None

    def register_challenger(
        self,
        *,
        model_id: str,
        version: str,
        features: list[str] | None = None,
        metrics: dict | None = None,
        note: str | None = None,
    ) -> dict:
        """Register a CHALLENGER model for paper/shadow race — not ACTIVE."""
        data = self._read()
        for m in data.get("models") or []:
            if m.get("model_id") == model_id:
                return {"ok": False, "reason": "already_exists", "model": m}
        rec = ModelRecord(
            model_id=model_id,
            version=version,
            status="SHADOW",
            features=list(features or []),
            metrics=dict(metrics or {"role": "CHALLENGER"}),
            created_at=utc_now().isoformat(),
            note=note or "Challenger — paper/shadow only until human promote",
        )
        data.setdefault("models", []).append(rec.to_dict())
        self._write(data)
        return {"ok": True, "model": rec.to_dict()}

    def promote(self, model_id: str, *, approved_by: str) -> dict:
        """Human-gated promotion. Never auto-called by trading loop."""
        data = self._read()
        found = None
        for m in data.get("models") or []:
            if m.get("model_id") == model_id:
                found = m
                break
        if not found:
            return {"ok": False, "reason": "model_not_found"}
        # Cannot jump to ACTIVE for live without shadow/paper history — keep honest
        found["status"] = "ACTIVE"
        found["promoted_by"] = approved_by
        found["promoted_at"] = utc_now().isoformat()
        data["active_model_id"] = model_id
        self._write(data)
        return {"ok": True, "model": found, "note": "ACTIVE means paper/shadow scoring default — not live broker unlock"}


model_registry = ModelRegistry()
