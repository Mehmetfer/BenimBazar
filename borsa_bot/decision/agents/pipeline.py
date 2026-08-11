"""DecisionAgent + TradePlannerAgent + Outcome/Learning/Health agents."""

from __future__ import annotations

import time
from typing import Any

from decision.agents import AgentResult, BaseAgent
from decision.reason import reason_over_opportunity
from decision.opportunity import RankedOpportunity


class DecisionAgent(BaseAgent):
    agent_id = "DecisionAgent"

    def run(
        self,
        opp: RankedOpportunity,
        *,
        decision_id: str,
        context: dict[str, Any],
        row: dict[str, Any],
        debate: dict[str, Any] | None = None,
        governor: dict[str, Any] | None = None,
        quality: dict[str, Any] | None = None,
    ) -> AgentResult:
        t0 = time.perf_counter()
        reasoning = reason_over_opportunity(opp, decision_id=decision_id, context=context, row=row)
        action = reasoning.action
        debate = debate or {}
        governor = governor or {}
        quality = quality or {}

        # STRONG_BUY hard standard
        if action == "STRONG_BUY":
            if not quality.get("eligible_strong_buy"):
                action = "BUY"
                reasoning.reason_codes = list(reasoning.reason_codes) + ["STRONG_BUY_DOWNGRADED"]
            if governor.get("allow_strong_buy") is False:
                action = "BUY"
                reasoning.reason_codes = list(reasoning.reason_codes) + ["GOVERNOR_NO_STRONG_BUY"]
            if not debate.get("bull_beats_bear"):
                action = "WAIT"
                reasoning.reason_codes = list(reasoning.reason_codes) + ["BEAR_CASE_WINS"]

        if governor.get("verdict") == "BLOCK":
            action = "NO_TRADE"
            reasoning.reason_codes = list(reasoning.reason_codes) + ["GOVERNOR_BLOCK"]
            reasoning.can_trade_proposal = False

        if action == "BUY" and debate.get("data_conflict"):
            # conflict → controlled wait/buy downgrade already in reason; reinforce
            if float(debate.get("bear_score") or 0) >= float(debate.get("bull_score") or 0):
                action = "WAIT"
                reasoning.reason_codes = list(reasoning.reason_codes) + ["CONFLICT_WAIT"]

        reasoning.action = action
        reasoning.can_trade_proposal = action in {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL", "AL", "SAT"}
        # Attach debate invalidations
        for inv in (debate.get("bear_case") or [])[:4]:
            if inv not in reasoning.invalidations:
                reasoning.invalidations.append(inv)

        return AgentResult(
            self.agent_id,
            True,
            {"reasoning": reasoning.to_dict()},
            [],
            round((time.perf_counter() - t0) * 1000, 2),
        )


class TradePlannerAgent(BaseAgent):
    agent_id = "TradePlannerAgent"

    def run(self, row: dict[str, Any]) -> AgentResult:
        plan = row.get("ai_trade_plan") if isinstance(row.get("ai_trade_plan"), dict) else {}
        if not plan and isinstance(row.get("trade_plan"), dict):
            plan = row["trade_plan"]
        return AgentResult(
            self.agent_id,
            bool(plan) or row.get("stop") is not None,
            {
                "entry": row.get("entry") or plan.get("entry") or row.get("price"),
                "stop": row.get("stop") or plan.get("stop") or plan.get("stop_loss"),
                "target1": (plan.get("target1") or {}).get("price")
                if isinstance(plan.get("target1"), dict)
                else (plan.get("target1") or (row.get("targets") or [None])[0]),
                "target2": (plan.get("target2") or {}).get("price") if isinstance(plan.get("target2"), dict) else plan.get("target2"),
                "risk_reward": plan.get("risk_reward") or row.get("risk_reward"),
                "note": "Plan from existing trade_plan engine — RiskEngine sizes finally",
            },
            [],
        )


class OutcomeAgent(BaseAgent):
    agent_id = "OutcomeAgent"

    def run(self, memory: Any, *, symbol: str | None = None) -> AgentResult:
        recent = memory.recent(symbol=symbol, limit=10) if memory else []
        resolved = [r for r in recent if r.get("outcome")]
        return AgentResult(
            self.agent_id,
            True,
            {
                "recent": recent[:5],
                "resolved_n": len(resolved),
                "note": "Outcomes link later via DecisionMemory.mark_outcome — no auto code rewrite",
            },
            [],
        )


class LearningAgent(BaseAgent):
    agent_id = "LearningAgent"

    def run(self, trading: Any) -> AgentResult:
        try:
            rep = trading.predictions.reliability_report()
            payload = {
                "grade": getattr(rep, "grade", None),
                "sample_size": getattr(rep, "sample_size", 0),
                "sample_tier": getattr(rep, "sample_tier", None),
                "brier_score": getattr(rep, "brier_score", None),
                "historical_accuracy_pct": getattr(rep, "historical_accuracy_pct", None),
                "note": "Measures only — no automatic production model promotion",
            }
            return AgentResult(self.agent_id, True, payload, [])
        except Exception as exc:  # noqa: BLE001
            return AgentResult(self.agent_id, False, {}, [str(exc)])


class HealthAgent(BaseAgent):
    agent_id = "HealthAgent"

    def run(self, trading: Any, *, context: dict[str, Any]) -> AgentResult:
        score = 100.0
        notes: list[str] = []
        if not context.get("data_connected"):
            score -= 40
            notes.append("DATA_DISCONNECTED")
        if not context.get("data_fresh"):
            score -= 20
            notes.append("DATA_STALE")
        if context.get("risk_paused"):
            score -= 25
            notes.append("RISK_PAUSED")
        if context.get("kill_switch"):
            score = 0
            notes.append("KILL_SWITCH")
        try:
            trading.provider.source_meta()
        except Exception:  # noqa: BLE001
            score -= 15
            notes.append("PROVIDER_META_FAIL")
        score = max(0.0, min(100.0, score))
        return AgentResult(
            self.agent_id,
            score >= 40,
            {
                "health_score": score,
                "trading_disabled": score < 40,
                "components": {
                    "data": context.get("data_kind"),
                    "fresh": context.get("data_fresh"),
                    "risk_paused": context.get("risk_paused"),
                },
            },
            notes,
        )


class OpportunityAgent(BaseAgent):
    agent_id = "OpportunityAgent"

    def run(self, rows: list[dict[str, Any]], *, market_type: str, top_n: int = 8) -> AgentResult:
        from decision.opportunity import competitive_summary, rank_opportunities

        ranked = rank_opportunities(rows, market_type=market_type, top_n=top_n)
        return AgentResult(
            self.agent_id,
            True,
            {
                "ranked": [r.to_dict() for r in ranked],
                "competitive": competitive_summary(ranked),
                "n_input": len(rows),
                "n_ranked": len(ranked),
            },
            [],
        )
