"""AI Decision Engine — agentic observe → debate → decide → propose (ultra layer).

Does NOT submit broker orders. RiskEngine + PreTradeGate + AIGovernor remain in chain.
LLM never invents market data. confidence ≠ calibrated probability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

from config.settings import settings
from decision.activity import ActivityLog
from decision.agents.debate import DebateEngine
from decision.agents.market import MarketAgent
from decision.agents.pipeline import (
    DecisionAgent,
    HealthAgent,
    LearningAgent,
    OpportunityAgent,
    OutcomeAgent,
    TradePlannerAgent,
)
from decision.agents.regime import RegimeAgent
from decision.cost_governor import ai_cost_governor
from decision.governor import ai_governor
from decision.opportunity import RankedOpportunity, ranked_from_dict
from decision.packet import DecisionMemory, build_decision_packet, new_decision_id
from decision.quality import autonomy_dashboard_scores, score_decision_quality
from decision.reason import ReasoningResult
from decision.watchlist import AIWatchlist

try:
    from level7.engine import Level7Engine
except Exception:  # noqa: BLE001
    Level7Engine = None  # type: ignore[misc, assignment]


@dataclass
class AIDecisionCycleReport:
    cycle_id: str
    market_type: str
    status: str
    context: dict[str, Any] = field(default_factory=dict)
    regime: dict[str, Any] = field(default_factory=dict)
    governor: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    ranked: list[dict[str, Any]] = field(default_factory=list)
    competitive: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    activity: list[dict[str, Any]] = field(default_factory=list)
    autonomy: dict[str, Any] = field(default_factory=dict)
    learning: dict[str, Any] = field(default_factory=dict)
    command_center: dict[str, Any] = field(default_factory=dict)
    level7: dict[str, Any] = field(default_factory=dict)
    top_card: dict[str, Any] | None = None
    ai_status: str = "ACTIVE"
    autonomy_score_hint: int = 55
    fallback: str = "QUANT/TECHNICAL"
    note: str = (
        "Agentic AI proposes decisions from structured REAL features. "
        "AIGovernor → Data → Risk → PreTradeGate. No broker bypass. confidence ≠ probability."
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
        self.market_agent = MarketAgent()
        self.regime_agent = RegimeAgent()
        self.opportunity_agent = OpportunityAgent()
        self.debate_engine = DebateEngine()
        self.decision_agent = DecisionAgent()
        self.planner_agent = TradePlannerAgent()
        self.health_agent = HealthAgent()
        self.learning_agent = LearningAgent()
        self.outcome_agent = OutcomeAgent()
        self.level7 = Level7Engine(trading) if Level7Engine is not None else None
        self._last: AIDecisionCycleReport | None = None

    def status(self) -> dict[str, Any]:
        last = self._last.to_dict() if self._last else None
        return {
            "ai_status": (last or {}).get("ai_status") or "IDLE",
            "last_cycle": last,
            "watchlist": self.watchlist.list_items(),
            "recent_decisions": self.memory.recent(limit=8),
            "command_center": (last or {}).get("command_center"),
            "autonomy": (last or {}).get("autonomy"),
            "level7": (last or {}).get("level7") or (self.level7.status() if self.level7 else {}),
            "risk_bypass": False,
            "broker_direct": False,
            "fallback": (last or {}).get("fallback") or "QUANT/TECHNICAL",
            "note": "AI STATUS · agentic proposals · RiskEngine final · LIVE locked",
        }

    def analyze_symbol(self, symbol: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
        """Research mode: analyze one symbol with debate + plan (no order)."""
        cycle_id = f"RES-{uuid4().hex[:8]}"
        activity = ActivityLog()
        activity.add(f"Research mode for {symbol}")
        mkt = self.market_agent.run(self.trading, cycle_id=cycle_id)
        ctx = mkt.payload.get("market_context") or {}
        reg = self.regime_agent.run(self.trading, context=ctx).payload.get("regime") or {}
        row = row or {"symbol": symbol, "final_decision": "WAIT", "scores": {}, "mtf": {}, "opportunity": {}}
        debate = self.debate_engine.run(row, regime=reg).payload
        plan = self.planner_agent.run(row).payload
        quality = score_decision_quality(
            row=row, context={**ctx, "data_valid": mkt.ok}, debate=debate.get("debate"), regime=reg
        ).to_dict()
        activity.add("Bull/Bear/Critic debate completed", symbol=symbol)
        return {
            "symbol": symbol,
            "context": ctx,
            "regime": reg,
            "debate": debate.get("debate"),
            "technical": debate.get("technical"),
            "quant": debate.get("quant"),
            "trade_plan": plan,
            "quality": quality,
            "activity": activity.to_list(),
            "risk_bypass": False,
            "note": "Research only — not an order",
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
        activity = ActivityLog()
        activity.add(f"Cycle {cycle_id} start · market={market_type}")

        if not cost.allowed:
            report.status = "AI_COST_BLOCKED"
            report.ai_status = "BLOCKED"
            report.note = cost.reason
            report.activity = activity.to_list()
            self._last = report
            return report.to_dict()

        # MarketAgent
        mkt = self.market_agent.run(self.trading, cycle_id=cycle_id, market_type=market_type)
        ctx = mkt.payload.get("market_context") or {}
        report.context = ctx
        activity.add(mkt.payload.get("summary") or "Market context built")
        if not mkt.ok:
            report.status = "NO_TRADE_DATA"
            report.ai_status = "BLOCKED"
            report.note = "DATA invalid/unavailable — AI will not invent prices"
            report.activity = activity.to_list()
            self._last = report
            return report.to_dict()

        # Health + Regime
        health = self.health_agent.run(self.trading, context={**ctx, "data_valid": True}).payload
        report.health = health
        activity.add(f"System health score={health.get('health_score')}")
        if health.get("trading_disabled"):
            report.status = "TRADING_DISABLED"
            report.ai_status = "BLOCKED"
            report.activity = activity.to_list()
            self._last = report
            return report.to_dict()

        reg = self.regime_agent.run(self.trading, context=ctx).payload.get("regime") or {}
        report.regime = reg
        activity.add(f"Regime={reg.get('primary')} labels={','.join(reg.get('labels') or [])}")

        learning = self.learning_agent.run(self.trading).payload
        report.learning = learning
        outcomes = self.outcome_agent.run(self.memory).payload

        # Serialize rows
        ser_rows = self._normalize_rows(rows)
        activity.add(f"Scanning {len(ser_rows)} analyzed candidates (post deep scan)")

        # OpportunityAgent
        opp_res = self.opportunity_agent.run(ser_rows, market_type=market_type, top_n=top_n)
        ranked_dicts = opp_res.payload.get("ranked") or []
        report.ranked = ranked_dicts
        report.competitive = opp_res.payload.get("competitive") or {}
        report.watchlist = self.watchlist.rebuild_from_ranked(ranked_dicts, market_type=market_type)
        activity.add(f"Opportunities ranked: {len(ranked_dicts)}")

        # Governor (market-level)
        gov = ai_governor.evaluate(
            context={**ctx, "data_valid": True},
            regime=reg,
            system_health=health,
            model_tier=str(learning.get("sample_tier") or learning.get("grade") or ""),
        )
        report.governor = gov.to_dict()
        activity.add(f"AIGovernor={gov.verdict} reasons={','.join(gov.reasons[:4])}")

        ctx_d = {**ctx, "data_valid": True}
        by_sym = {str(r.get("symbol")): r for r in ser_rows}
        packets: list[dict[str, Any]] = []

        for rd in ranked_dicts[:5]:
            opp = ranked_from_dict(rd)
            row = by_sym.get(opp.symbol) or rd
            activity.add(f"Debating {opp.symbol}", symbol=opp.symbol)
            debate_payload = self.debate_engine.run(row, regime=reg).payload
            debate = debate_payload.get("debate") or {}
            activity.add(f"Bull score={debate.get('bull_score')} Bear score={debate.get('bear_score')}", symbol=opp.symbol)

            quality = score_decision_quality(row=row, context=ctx_d, debate=debate, regime=reg)
            # Per-symbol governor refine with debate
            gov_sym = ai_governor.evaluate(
                context=ctx_d,
                regime=reg,
                debate=debate,
                system_health=health,
                model_tier=str(learning.get("sample_tier") or ""),
            )

            did = new_decision_id()
            dec = self.decision_agent.run(
                opp,
                decision_id=did,
                context=ctx_d,
                row=row,
                debate=debate,
                governor=gov_sym.to_dict(),
                quality=quality.to_dict(),
            )
            reasoning_d = dec.payload.get("reasoning") or {}
            reasoning = ReasoningResult(
                **{k: reasoning_d[k] for k in ReasoningResult.__dataclass_fields__ if k in reasoning_d}
            )

            # Stability
            prev = self.memory.recent(symbol=opp.symbol, limit=1)
            if prev:
                last_action = str(prev[0].get("action") or "")
                if last_action in {"BUY", "STRONG_BUY", "AL"} and reasoning.action in {"SELL", "STRONG_SELL"}:
                    reasoning.reason_codes = list(reasoning.reason_codes) + ["DECISION_INSTABILITY_CHECK"]

            plan = self.planner_agent.run(row).payload
            alts = [ranked_from_dict(x) for x in ranked_dicts]
            packet = build_decision_packet(
                reasoning=reasoning,
                context=self._ctx_obj(ctx, cycle_id, market_type),
                opportunity=opp,
                row=row,
                alternatives=alts,
                model_version=str(getattr(settings, "prediction_model_version", "heuristic_ensemble")),
            )
            # Enrich packet dict with debate/quality/governor
            pd = packet.to_dict()
            pd["bull_case"] = debate.get("bull_case")
            pd["bear_case"] = debate.get("bear_case")
            pd["critic"] = debate.get("critic")
            pd["quality"] = quality.to_dict()
            pd["governor"] = gov_sym.to_dict()
            pd["trade_plan_agent"] = plan
            pd["risk_engine_bypassed"] = False
            assert pd["risk_engine_bypassed"] is False
            self.memory.record(packet)
            packets.append(pd)
            activity.add(
                f"Decision={reasoning.action} quality={quality.total} gov={gov_sym.verdict}",
                symbol=opp.symbol,
            )

        report.decisions = packets
        report.activity = activity.to_list()
        report.autonomy = autonomy_dashboard_scores(
            context_ok=True,
            discovery_n=len(ser_rows),
            decisions_n=len(packets),
            prediction_tier=str(learning.get("sample_tier") or learning.get("grade") or "INSUFFICIENT"),
            risk_awareness=94.0 if gov.verdict != "BLOCK" else 60.0,
        )
        report.autonomy_score_hint = int(report.autonomy.get("total_autonomy") or 55)
        report.command_center = {
            "market": reg.get("primary"),
            "data": f"{ctx.get('data_kind')} · {'VERIFIED' if ctx.get('data_fresh') else 'STALE'}",
            "symbols_scanned": len(ser_rows),
            "opportunities": len(ranked_dicts),
            "strong_setups": sum(1 for p in packets if p.get("action") == "STRONG_BUY"),
            "top": [
                {"symbol": p.get("symbol"), "action": p.get("action"), "quality": (p.get("quality") or {}).get("total")}
                for p in packets[:3]
            ],
            "governor": gov.verdict,
            "health_score": health.get("health_score"),
            "outcomes_resolved": outcomes.get("resolved_n"),
            "fallback": "QUANT/TECHNICAL (LLM disabled)",
        }

        if packets:
            top = packets[0]
            q = top.get("quality") or {}
            report.top_card = {
                "symbol": top.get("symbol"),
                "ai_decision": top.get("action"),
                "confidence": top.get("confidence"),
                "confidence_label": "Model/heuristic score — NOT win probability",
                "calibrated_probability": None,
                "expected_value": top.get("expected_value"),
                "expected_move_pct": top.get("expected_return"),
                "risk_pct": top.get("expected_risk"),
                "entry": top.get("entry"),
                "stop": top.get("stop"),
                "target": top.get("target"),
                "risk_reward": top.get("risk_reward"),
                "regime": top.get("regime"),
                "strategy": top.get("strategy"),
                "reason_codes": top.get("reason_codes"),
                "bull_case": top.get("bull_case"),
                "bear_case": top.get("bear_case"),
                "critic": top.get("critic"),
                "counter_argument": top.get("counter_argument"),
                "quality": q,
                "why_not_others": top.get("alternatives")[:3],
                "governor": top.get("governor"),
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

        report.status = "OK" if gov.verdict != "BLOCK" else "GOVERNOR_BLOCKED"
        report.ai_status = "ACTIVE" if gov.verdict != "BLOCK" else "BLOCKED"
        report.fallback = "QUANT/TECHNICAL"

        # Level 7 research / hypothesis / diagnostics layer (propose-only)
        if self.level7 is not None:
            top_row = by_sym.get((packets[0] or {}).get("symbol")) if packets else (ser_rows[0] if ser_rows else None)
            dq = float(((packets[0] or {}).get("quality") or {}).get("total") or 70) if packets else 55.0
            try:
                report.level7 = self.level7.run_cycle(
                    context=ctx_d,
                    regime=reg,
                    health=health,
                    learning=learning,
                    top_row=top_row,
                    decision_quality_avg=dq,
                    seed_research=True,
                )
                # Enrich command center
                sc = report.level7.get("scorecard") or {}
                report.command_center["level7_score"] = sc.get("level7_autonomy_score")
                report.command_center["autonomy_state"] = (report.level7.get("autonomy") or {}).get("state")
                report.command_center["research_open"] = len(report.level7.get("research_questions") or [])
                report.command_center["hypotheses"] = len(report.level7.get("hypotheses") or [])
            except Exception as exc:  # noqa: BLE001
                report.level7 = {"status": "ERROR", "error": str(exc), "risk_bypass": False}

        self._last = report
        return report.to_dict()

    def _normalize_rows(self, rows: list[Any]) -> list[dict[str, Any]]:
        if rows and hasattr(rows[0], "symbol") and hasattr(self.trading, "_serialize"):
            try:
                return [self.trading._serialize(d) for d in rows]  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
        ser_rows: list[dict[str, Any]] = []
        for r in rows:
            if isinstance(r, dict):
                ser_rows.append(dict(r))
            else:
                ser_rows.append(
                    {
                        "symbol": getattr(r, "symbol", None),
                        "final_decision": getattr(r, "final_decision", None)
                        or getattr(getattr(r, "decision", None), "value", None),
                        "buy_score": getattr(r, "buy_score", None),
                        "ai_confidence": getattr(r, "ai_confidence", None),
                        "regime": getattr(getattr(r, "regime", None), "value", getattr(r, "regime", None)),
                        "mtf": getattr(r, "mtf", {}) or {},
                        "opportunity": getattr(r, "opportunity", None).__dict__
                        if getattr(r, "opportunity", None) and hasattr(getattr(r, "opportunity", None), "__dict__")
                        else {},
                        "scores": getattr(r, "scores", None).__dict__
                        if getattr(r, "scores", None) and hasattr(getattr(r, "scores", None), "__dict__")
                        else {},
                        "is_favorite": getattr(r, "is_favorite", False),
                        "entry": getattr(r, "price", None),
                        "stop": getattr(r, "stop_price", None),
                        "targets": [getattr(r, "target_price", None)] if getattr(r, "target_price", None) else [],
                        "risk_reward": getattr(r, "risk_reward", None),
                        "spread_pct": getattr(r, "spread_pct", None),
                    }
                )
        return ser_rows

    def _ctx_obj(self, ctx: dict[str, Any], cycle_id: str, market_type: str) -> Any:
        from decision.context import ContextPack

        return ContextPack(
            cycle_id=cycle_id,
            market_type=market_type.upper(),
            observed_at=str(ctx.get("observed_at") or ""),
            market_regime=str(ctx.get("market_regime") or "UNKNOWN"),
            data_kind=str(ctx.get("data_kind") or "UNKNOWN"),
            data_fresh=bool(ctx.get("data_fresh")),
            data_connected=bool(ctx.get("data_connected")),
            provider_class=str(ctx.get("provider_class") or ""),
            market_session=str(ctx.get("market_session") or "UNKNOWN"),
            equity=float(ctx.get("equity") or 0),
            cash=float(ctx.get("cash") or 0),
            open_positions=int(ctx.get("open_positions") or 0),
            daily_pnl=float(ctx.get("daily_pnl") or 0),
            drawdown_pct=float(ctx.get("drawdown_pct") or 0),
            risk_paused=bool(ctx.get("risk_paused")),
            kill_switch=bool(ctx.get("kill_switch")),
            capital_mode=str(ctx.get("capital_mode") or "UNKNOWN"),
            prediction_tier=str(ctx.get("prediction_tier") or "INSUFFICIENT"),
            prediction_sample=int(ctx.get("prediction_sample") or 0),
            unknowns=list(ctx.get("unknowns") or []),
        )


def run_ai_decision_cycle(trading: Any, rows: list[Any], **kwargs: Any) -> dict[str, Any]:
    return AIDecisionEngine(trading).run_from_scan_rows(rows, **kwargs)
