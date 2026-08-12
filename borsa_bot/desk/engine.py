"""Institutional desk engine — orchestrates committee + pipeline + briefing."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from decision.agents.debate import DebateEngine
from decision.agents.market import MarketAgent
from decision.agents.regime import RegimeAgent
from decision.context import build_context_pack
from desk.briefing import generate_daily_briefing
from desk.models import ProfessionalDecision
from desk.pipeline import FinalDecisionPipeline
from desk.session import current_session_mode


def _row_from_decision(d: Any) -> dict[str, Any]:
    """Convert SymbolDecision (or dict) to committee row."""
    if isinstance(d, dict):
        return d
    opp = d.opportunity
    opp_d = (
        {
            "expected_value": opp.expected_value,
            "expected_return_pct": opp.expected_return_pct,
            "expected_loss_pct": opp.expected_loss_pct,
            "risk_reward": opp.risk_reward,
            "p_win": opp.p_win,
            "volatility_pct": opp.volatility_pct,
        }
        if opp
        else {}
    )
    scores = d.scores
    scores_d = asdict(scores) if scores else {}
    plan = d.trade_plan
    plan_d = asdict(plan) if plan else {}
    return {
        "symbol": d.symbol,
        "name": d.name,
        "sector": d.sector,
        "price": d.price,
        "bid": getattr(d, "bid", None),
        "ask": getattr(d, "ask", None),
        "spread_pct": getattr(d, "spread_pct", None),
        "final_decision": d.final_decision or d.decision.value,
        "decision": d.decision.value,
        "signal": d.signal.value,
        "regime": d.regime.value if hasattr(d.regime, "value") else str(d.regime),
        "buy_score": d.buy_score,
        "sell_score": d.sell_score,
        "ai_confidence": d.ai_confidence,
        "stop_price": d.stop_price,
        "target_price": d.target_price,
        "explanation": d.explanation,
        "scores": scores_d,
        "opportunity": opp_d,
        "trade_plan": plan_d,
        "mtf": d.mtf,
        "conflict": d.conflict,
        "strategy_votes": d.strategy_votes,
        "risks": d.risks,
        "risk": d.risk.value if hasattr(d.risk, "value") else str(d.risk),
        "data_source_kind": d.data_source_kind,
    }


class InstitutionalDeskEngine:
    """Top-level institutional broker / quant desk facade."""

    def __init__(self, trading: Any) -> None:
        self.trading = trading
        self.pipeline = FinalDecisionPipeline()
        self.market_agent = MarketAgent()
        self.regime_agent = RegimeAgent()
        self.debate_engine = DebateEngine()
        self._last_briefing: dict[str, Any] | None = None

    def _portfolio_context(self) -> dict[str, Any]:
        try:
            snap = self.trading.paper_wallet()
            return {
                "open_positions": snap.get("open_positions") or len(snap.get("positions") or []),
                "max_open_positions": snap.get("max_open_positions"),
                "exposure_pct": snap.get("exposure_pct") or 0,
                "daily_loss_pct": self.trading.ledger.daily_loss_pct(),
                "drawdown_pct": snap.get("drawdown_pct") or self.trading.ledger.drawdown_pct(),
                "cash": snap.get("cash"),
                "equity": snap.get("equity"),
            }
        except Exception:  # noqa: BLE001
            return {}

    def evaluate_symbol(self, symbol: str, *, row: dict[str, Any] | None = None) -> ProfessionalDecision:
        """Full desk evaluation for one symbol."""
        cycle_id = f"desk-{symbol}"
        mkt = self.market_agent.run(self.trading, cycle_id=cycle_id)
        ctx = mkt.payload.get("market_context") or {}
        reg = (self.regime_agent.run(self.trading, context=ctx).payload or {}).get("regime") or {}

        if row is None:
            decisions = self.trading.scan(symbols=[symbol])
            if not decisions:
                row = {"symbol": symbol, "final_decision": "NO_TRADE", "scores": {}, "opportunity": {}}
            else:
                row = _row_from_decision(decisions[0])

        debate = self.debate_engine.run(row, regime=reg).payload.get("debate") or {}
        portfolio = self._portfolio_context()

        result = self.pipeline.run(
            row,
            trading=self.trading,
            context=ctx,
            portfolio=portfolio,
            debate=debate,
            regime=reg,
        )

        opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        entry = result.get("entry") or {}
        consensus = result.get("consensus") or {}

        decision = ProfessionalDecision(
            decision_id=ProfessionalDecision.new_id(),
            symbol=symbol,
            decision=result.get("final_decision") or "NO_TRADE",
            confidence=float(consensus.get("confidence") or 0),
            expected_edge=float(opp.get("expected_value")) if opp.get("expected_value") is not None else None,
            risk_reward=float(opp.get("risk_reward")) if opp.get("risk_reward") is not None else None,
            market_regime=str(reg.get("primary") or row.get("regime") or "UNKNOWN"),
            signal_quality=float(result.get("signal_quality") or 0),
            liquidity_score=float(scores.get("liquidity")) if scores.get("liquidity") is not None else None,
            execution_score=float(entry.get("entry_quality")) if entry.get("entry_quality") is not None else None,
            portfolio_fit=80.0 if portfolio.get("open_positions", 0) < portfolio.get("max_open_positions", 99) else 30.0,
            risk_status="VETO" if consensus.get("veto") else "APPROVED",
            entry_action=str(entry.get("action") or "NO_TRADE"),
            order_type=str(entry.get("order_type") or "LIMIT"),
            committee_votes=result.get("committee_votes") or [],
            pipeline=result.get("stages") or [],
            thesis=result.get("thesis"),
            veto=bool(consensus.get("veto")),
            veto_reason=str(consensus.get("veto_reason") or ""),
            session_mode=current_session_mode().value,
            audit={
                "who": "InstitutionalDeskEngine",
                "what": result.get("final_decision"),
                "when": ProfessionalDecision.new_id(),
                "why": consensus.get("veto_reason") or entry.get("reason"),
                "data": ctx.get("data_kind"),
                "model": "committee+pipeline",
                "version": "desk-v1",
                "risk": consensus.get("veto_reason") or "",
            },
        )
        return decision

    def evaluate_scan(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Evaluate top scan rows through the full pipeline."""
        decisions = self.trading.scan()
        rows = [_row_from_decision(d) for d in decisions[:limit]]
        mkt = self.market_agent.run(self.trading, cycle_id="desk-scan")
        ctx = mkt.payload.get("market_context") or {}
        reg = (self.regime_agent.run(self.trading, context=ctx).payload or {}).get("regime") or {}
        portfolio = self._portfolio_context()
        out: list[dict[str, Any]] = []
        for row in rows:
            debate = self.debate_engine.run(row, regime=reg).payload.get("debate") or {}
            r = self.pipeline.run(row, trading=self.trading, context=ctx, portfolio=portfolio, debate=debate, regime=reg)
            r["symbol"] = row.get("symbol")
            out.append(r)
        return out

    def briefing(self) -> dict[str, Any]:
        decisions = self.trading.scan()
        rows = [_row_from_decision(d) for d in decisions[:25]]
        pipelines = self.evaluate_scan(limit=25)
        self._last_briefing = generate_daily_briefing(
            trading=self.trading,
            scan_rows=rows,
            pipeline_results=pipelines,
        )
        return self._last_briefing
