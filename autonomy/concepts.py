"""Normalized Observation / Evidence / Decision concepts shared across F6/F7."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Observation:
    source: str
    kind: str
    message: str
    evidence: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "message": self.message,
            "evidence": list(self.evidence),
            "timestamp": self.timestamp,
        }


@dataclass
class Evidence:
    items: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def add(self, item: str) -> None:
        self.items.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {"items": list(self.items), "confidence": self.confidence}


@dataclass
class DecisionRecord:
    action: str
    confidence: float
    risk: str
    reason: str
    evidence: Evidence = field(default_factory=Evidence)
    result: str = ""
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "risk": self.risk,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
            "result": self.result,
            "feedback": self.feedback,
        }
