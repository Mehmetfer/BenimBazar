"""GÖREV 20 — Decision replay store (explain why BUY/NO_TRADE was chosen)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DecisionRecord:
    record_id: str
    timestamp: float
    symbol: str
    market_state: Dict[str, Any]
    features: Dict[str, Any]
    regime: Dict[str, Any]
    signals: Dict[str, Any]
    risk: Dict[str, Any]
    decision: str
    confidence: float
    reason: str
    evidence: List[str] = field(default_factory=list)
    execution: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DecisionReplayStore:
    """Persist paper decisions for later Replay Decision answers."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path("borsa_bot/.decision_replay.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: List[DecisionRecord] = []

    def save_from_decision(self, decision_dict: Dict[str, Any], *, execution: Optional[Dict[str, Any]] = None) -> DecisionRecord:
        regime = decision_dict.get("regime") or {}
        signals = decision_dict.get("composite_signal") or {}
        market = decision_dict.get("market_state") or {}
        features = {
            "unknown_fields": market.get("unknown_fields", []),
            "regime": regime.get("regime"),
            "signal_score": signals.get("score"),
            "signal_conflict": signals.get("conflict"),
        }
        rec = DecisionRecord(
            record_id=f"dr-{uuid.uuid4().hex[:12]}",
            timestamp=time.time(),
            symbol=str(decision_dict.get("symbol") or ""),
            market_state=market,
            features=features,
            regime=regime,
            signals=signals,
            risk=decision_dict.get("risk_state") or {},
            decision=str(decision_dict.get("decision")),
            confidence=float(decision_dict.get("confidence") or 0),
            reason=str(decision_dict.get("reason") or ""),
            evidence=list(decision_dict.get("evidence") or []),
            execution=execution
            or {
                "mode": "PAPER",
                "live_trading": False,
                "position_size": decision_dict.get("position_size", 0),
            },
            result={},
        )
        self._append(rec)
        self._cache.append(rec)
        return rec

    def attach_result(self, record_id: str, result: Dict[str, Any]) -> Optional[DecisionRecord]:
        # Update cache + rewrite file for simplicity (small paper logs)
        updated = None
        for rec in self._cache:
            if rec.record_id == record_id:
                rec.result = dict(result)
                updated = rec
                break
        if updated is None:
            # load from disk
            for rec in self.all():
                if rec.record_id == record_id:
                    rec.result = dict(result)
                    updated = rec
                    self._cache = self.all()
                    break
        if updated is not None:
            self._rewrite_all(self._cache if self._cache else self.all())
        return updated

    def replay(self, record_id: str) -> Dict[str, Any]:
        rec = self.get(record_id)
        if rec is None:
            return {"ok": False, "error": "not_found", "record_id": record_id}
        return {
            "ok": True,
            "record_id": rec.record_id,
            "question": f"Why did the system decide {rec.decision}?",
            "answer": {
                "decision": rec.decision,
                "confidence": rec.confidence,
                "reason": rec.reason,
                "evidence": rec.evidence,
                "regime": rec.regime,
                "signals": {
                    "direction": rec.signals.get("direction"),
                    "score": rec.signals.get("score"),
                    "conflict": rec.signals.get("conflict"),
                    "conflict_reasons": rec.signals.get("conflict_reasons"),
                    "components": rec.signals.get("components"),
                },
                "risk": rec.risk,
                "execution": rec.execution,
                "result": rec.result,
                "features": rec.features,
                "timestamp": rec.timestamp,
                "symbol": rec.symbol,
            },
            "live_trading": False,
        }

    def get(self, record_id: str) -> Optional[DecisionRecord]:
        for rec in self._cache:
            if rec.record_id == record_id:
                return rec
        for rec in self.all():
            if rec.record_id == record_id:
                return rec
        return None

    def all(self) -> List[DecisionRecord]:
        if not self.path.exists():
            return []
        out: List[DecisionRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            out.append(DecisionRecord(**data))
        return out

    def _append(self, rec: DecisionRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_all(self, records: List[DecisionRecord]) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
