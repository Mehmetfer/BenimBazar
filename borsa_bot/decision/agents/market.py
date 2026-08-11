"""MarketAgent — What is happening now? Uses existing context + provider meta only."""

from __future__ import annotations

import time
from typing import Any

from decision.agents import AgentResult, BaseAgent
from decision.context import build_context_pack


class MarketAgent(BaseAgent):
    agent_id = "MarketAgent"

    def run(self, trading: Any, *, cycle_id: str, market_type: str = "BIST") -> AgentResult:
        t0 = time.perf_counter()
        ctx = build_context_pack(trading, cycle_id=cycle_id, market_type=market_type)
        notes = list(ctx.unknowns)
        if not ctx.data_valid:
            notes.append("DATA_INVALID")
        return AgentResult(
            agent_id=self.agent_id,
            ok=ctx.data_valid,
            payload={
                "market_context": ctx.to_dict(),
                "data_valid": ctx.data_valid,
                "summary": (
                    f"regime={ctx.market_regime} kind={ctx.data_kind} "
                    f"fresh={ctx.data_fresh} positions={ctx.open_positions}"
                ),
            },
            notes=notes,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
