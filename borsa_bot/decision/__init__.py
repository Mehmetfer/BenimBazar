"""AI Decision Engine — Phase 1–4 glue.

Observes structured REAL data → ranks opportunities → reasons → proposes
trade plans. NEVER bypasses RiskEngine / PreTradeGate. NEVER invents prices.
LLM (if enabled later) may only explain structured packets — not fabricate MD.
"""

from __future__ import annotations

from decision.context import ContextPack, build_context_pack
from decision.engine import AIDecisionEngine, run_ai_decision_cycle
from decision.packet import DecisionMemory, DecisionPacket
from decision.watchlist import AIWatchlist

__all__ = [
    "AIDecisionEngine",
    "AIWatchlist",
    "ContextPack",
    "DecisionMemory",
    "DecisionPacket",
    "build_context_pack",
    "run_ai_decision_cycle",
]
