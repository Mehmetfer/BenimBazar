"""Agent package — single-responsibility AI agents (no broker/secret access)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentResult:
    agent_id: str
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseAgent:
    agent_id: str = "base"

    def run(self, **kwargs: Any) -> AgentResult:  # pragma: no cover
        raise NotImplementedError


__all__ = ["AgentResult", "BaseAgent"]
