"""Phase 5 — AdversarialAgent: actively try to refute BUY/SELL (extends debate)."""

from __future__ import annotations

from typing import Any

from decision.agents import AgentResult, BaseAgent
from decision.agents.debate import DebateEngine


class AdversarialAgent(BaseAgent):
    """Red-team: Why is this decision wrong? Never invents market data."""

    agent_id = "AdversarialAgent"

    def __init__(self) -> None:
        self.debate = DebateEngine()

    def run(
        self,
        row: dict[str, Any],
        *,
        regime: dict[str, Any] | None = None,
        action: str | None = None,
    ) -> AgentResult:
        debate_payload = self.debate.run(row, regime=regime).payload
        debate = debate_payload.get("debate") or {}
        action = str(action or row.get("final_decision") or row.get("decision") or "WAIT").upper()
        attacks: list[str] = []

        if action in {"BUY", "STRONG_BUY", "AL"}:
            attacks.append("Why is this BUY wrong?")
            for b in debate.get("bear_case") or []:
                attacks.append(f"REFUTE_BUY: {b}")
            if action == "STRONG_BUY":
                attacks.append("What evidence would invalidate this STRONG_BUY?")
                attacks.extend([f"INVALIDATION: {x}" for x in (debate.get("bear_case") or [])[:3]])
            if debate.get("data_conflict"):
                attacks.append("MTF conflict undermines directional conviction")
            if not debate.get("bull_beats_bear"):
                attacks.append("Bear case dominates — BUY thesis fragile")
        elif action in {"SELL", "STRONG_SELL", "SAT"}:
            attacks.append("Why is this SELL wrong?")
            for b in debate.get("bull_case") or []:
                attacks.append(f"REFUTE_SELL: {b}")
        else:
            attacks.append("WAIT/NO_TRADE — adversarial check: is inaction missing a high-EV setup?")
            if debate.get("bull_beats_bear") and float(debate.get("bull_score") or 0) > 70:
                attacks.append("Bull evidence strong while waiting — opportunity cost?")

        # Always append uncertainty principle
        attacks.append("No guarantee — positive EV and risk control only")

        model_conflict = bool(debate.get("data_conflict")) or (
            float(debate.get("bull_score") or 0) > 0
            and abs(float(debate.get("bull_score") or 0) - float(debate.get("bear_score") or 0)) < 8
        )

        return AgentResult(
            self.agent_id,
            True,
            {
                "action_under_attack": action,
                "attacks": attacks,
                "debate": debate,
                "technical": debate_payload.get("technical"),
                "quant": debate_payload.get("quant"),
                "model_conflict": model_conflict,
                "confidence_haircut": 0.15 if model_conflict else 0.0,
                "note": "Adversarial output is critique — not market data",
            },
            attacks[:3],
        )
