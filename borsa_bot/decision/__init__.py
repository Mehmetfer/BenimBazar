"""AI Decision Engine — agentic observe → debate → decide → propose.

Observes structured REAL data → ranks opportunities → debates → reasons → proposes
trade plans. NEVER bypasses RiskEngine / PreTradeGate / AIGovernor. NEVER invents prices.
LLM (if enabled later) may only explain structured packets — not fabricate MD.
confidence ≠ calibrated probability. WHEN UNCERTAIN → DO NOT TRADE.
"""

from __future__ import annotations

from decision.context import ContextPack, build_context_pack
from decision.engine import AIDecisionEngine, run_ai_decision_cycle
from decision.governor import AIGovernor, ai_governor
from decision.packet import DecisionMemory, DecisionPacket
from decision.watchlist import AIWatchlist

__all__ = [
    "AIDecisionEngine",
    "AIGovernor",
    "AIWatchlist",
    "ContextPack",
    "DecisionMemory",
    "DecisionPacket",
    "ai_governor",
    "build_context_pack",
    "run_ai_decision_cycle",
]
