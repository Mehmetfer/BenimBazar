"""AI Decision Engine — observe → rank → reason → propose (Phases 1–4).

Does NOT submit broker orders. RiskEngine + PreTradeGate remain authoritative.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

from config.settings import settings
from decision.context import ContextPack, build_context_pack
from decision.cost_governor import ai_cost_governor
from decision.opportunity import competitive_summary, rank_opportunities
from decision.packet import DecisionMemory, DecisionPacket, build_decision_packet, new_decision_id
from decision.reason import reason_over_opportunity
from decision.watchlist import AIWatchlist


@dataclass
class AIDecisionCycleReport:
    cycle_id: str
    market_type: str
    status: str
    context: dict[str, Any] = field(default_factory=dict)
    ranked: list[dict[str, Any]] = field(default_factory=list)
    competitive: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    top_card: dict[str, Any] | None = None
    ai_status: str = "ACTIVE"
    autonomy_score_hint: int = 50
    note: str = (
        "AI proposes decisions from structured REAL features. "
        "RiskEngine cannot be bypassed. confidence ≠ probability. No LLM price invention."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIDecisionEngine:
    def __init__(
        self,
        trading: Any,
        *,
        memory: Optional[DecisionMemory] = None,
        watchlist: Optional[AIWatchlist] = None,
    ) -> None:
        self.trading = trading
        self.memory = memory or DecisionMemory()
        self.watchlist = watchlist or AIWatchlist()
        self._last: AIDecisionCycleReport | None = None

    def status(self) -> dict[str, Any]:
        last = self._last.to_dict() if self._last else None
        return {
            "ai_status": (last or {}).get("ai_status") or "IDLE",
            "last_cycle": last,
            "watchlist": self.watchlist.list_items(),
            "recent_decisions": self.memory.recent(limit=8),
            "risk_bypass": False,
            "broker_direct": False,
            "note": "AI STATUS · proposals only · paper/shadow via execution engine",
        }

    def run_from_scan_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        market_type: str = "BIST",
        top_n: int = 8,
        cycle_id: str | None = None,
    ) -> dict[str, Any]:
        cost = ai_cost_governor.allow(want_llm=False)
        cycle_id = cycle_id or f"AI-{uuid4().hex[:10]}"
        report = AIDecisionCycleReport(cycle_id=cycle_id, market_type=market_type.upper(), status="RUNNING")

        if not cost.allowed:
            report.status = "AI_COST_BLOCKED"
            report.ai_status = "BLOCKED"
            report.note = cost.reason
            self._last = report
            return report.to_dict()

        ctx = build_context_pack(self.trading, cycle_id=cycle_id, market_type=market_type)
        report.context = ctx.to_dict()
        if not ctx.data_valid:
            report.status = "NO_TRADE_DATA"
            report.ai_status = "BLOCKED"
            report.note = "DATA invalid/unavailable — AI will not invent prices"
            self._last = report
            return report.to_dict()

        # Prefer serialized decision dicts from TradingService
        ser_rows: list[dict[str, Any]] = []
        for r in rows:
            if hasattr(r, "__dict__") and not isinstance(r, dict):
                # SymbolDecision — use service serializer when available
                ser = getattr(self.trading, "serialize_decision", None)
                if callable(ser):
                    ser_rows.append(ser(r))
                else:
                    ser_rows.append(
                        {
                            "symbol": getattr(r, "symbol", None),
                            "final_decision": getattr(r, "final_decision", None) or getattr(getattr(r, "decision", None), "value", None),
                            "buy_score": getattr(r, "buy_score", None),
                            "ai_confidence": getattr(r, "ai_confidence", None),
                            "regime": getattr(getattr(r, "regime", None), "value", getattr(r, "regime", None)),
                            "mtf": getattr(r, "mtf", {}) or {},
                            "opportunity": getattr(r, "opportunity", None).__dict__
                            if getattr(r, "opportunity", None) and hasattr(getattr(r, "opportunity", None), "__dict__")
                            else getattr(r, "opportunity", None),
                            "ai_trade_plan": None,
                            "is_favorite": getattr(r, "is_favorite", False),
                            "scores": getattr(r, "scores", None).__dict__
                            if getattr(r, "scores", None) and hasattr(getattr(r, "scores", None), "__dict__")
                            else {},
                            "entry": getattr(r, "price", None),
                            "stop": getattr(r, "stop_price", None),
                            "targets": [getattr(r, "target_price", None)] if getattr(r, "target_price", None) else [],
                            "risk_reward": getattr(r, "risk_reward", None),
                            "spread_pct": getattr(r, "spread_pct", None),
                        }
                    )
            else:
                ser_rows.append(dict(r))

        # Enrich with TradingService.serialize when we have SymbolDecision list
        if rows and hasattr(rows[0], "symbol") and hasattr(self.trading, "_serialize"):
            try:
                ser_rows = [self.trading._serialize(d) for d in rows]  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass

        ranked = rank_opportunities(ser_rows, market_type=market_type, top_n=top_n)
        report.ranked = [r.to_dict() for r in ranked]
        report.competitive = competitive_summary(ranked)
        report.watchlist = self.watchlist.rebuild_from_ranked(ranked, market_type=market_type)

        ctx_d = {**ctx.to_dict(), "data_valid": ctx.data_valid}
        packets: list[DecisionPacket] = []
        by_sym = {str(r.get("symbol")): r for r in ser_rows}

        for opp in ranked[:5]:
            did = new_decision_id()
            reasoning = reason_over_opportunity(opp, decision_id=did, context=ctx_d, row=by_sym.get(opp.symbol) or {})
            # Stability: if last decision flipped wildly, annotate
            prev = self.memory.recent(symbol=opp.symbol, limit=1)
            if prev:
                last_action = str(prev[0].get("action") or "")
                if last_action in {"BUY", "STRONG_BUY", "AL"} and reasoning.action in {"SELL", "STRONG_SELL"}:
                    reasoning.reason_codes = list(reasoning.reason_codes) + ["DECISION_INSTABILITY_CHECK"]
                    reasoning.invalidations = list(reasoning.invalidations) + ["FAST_FLIP"]
            packet = build_decision_packet(
                reasoning=reasoning,
                context=ctx,
                opportunity=opp,
                row=by_sym.get(opp.symbol) or {},
                alternatives=ranked,
                model_version=str(getattr(settings, "prediction_model_version", "heuristic_ensemble")),
            )
            assert packet.risk_engine_bypassed is False
            self.memory.record(packet)
            packets.append(packet)

        report.decisions = [p.to_dict() for p in packets]
        if packets:
            top = packets[0]
            report.top_card = {
                "symbol": top.symbol,
                "ai_decision": top.action,
                "confidence": top.confidence,
                "confidence_label": "Model/heuristic score — NOT win probability",
                "calibrated_probability": None,
                "expected_value": top.expected_value,
                "expected_move_pct": top.expected_return,
                "risk_pct": top.expected_risk,
                "entry": top.entry,
                "stop": top.stop,
                "target": top.target,
                "risk_reward": top.risk_reward,
                "regime": top.regime,
                "strategy": top.strategy,
                "reason_codes": top.reason_codes,
                "counter_argument": top.counter_argument,
                "why_not_others": top.alternatives[:3],
                "risk_bypass": False,
            }
        else:
            report.top_card = {
                "symbol": None,
                "ai_decision": "NO_TRADE",
                "reason_codes": ["NO_CLEAR_EDGE"],
                "confidence_label": "No forced trade",
                "risk_bypass": False,
            }

        report.status = "OK"
        report.ai_status = "ACTIVE"
        # Analyst-level autonomy while paper proposals exist without live broker
        report.autonomy_score_hint = 55 if packets else 45
        self._last = report
        return report.to_dict()


def run_ai_decision_cycle(trading: Any, rows: list[Any], **kwargs: Any) -> dict[str, Any]:
    return AIDecisionEngine(trading).run_from_scan_rows(rows, **kwargs)
