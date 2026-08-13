"""GÖREV 30 F6 side — observe→decide→paper→feedback→replay orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from decision.engine import DecisionAction, DecisionOutput, decide_from_state
from decision.feedback import DecisionFeedbackLoop
from decision.observe import observe_market
from decision.replay import DecisionReplayStore
from decision.risk_gate import RiskLimits


@dataclass
class PaperExecutionResult:
    executed: bool
    mode: str = "PAPER"
    fill_price: Optional[float] = None
    quantity: float = 0.0
    pnl: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executed": self.executed,
            "mode": self.mode,
            "fill_price": self.fill_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "note": self.note,
            "live_trading": False,
        }


@dataclass
class F6CycleResult:
    decision: DecisionOutput
    execution: PaperExecutionResult
    record_id: str
    feedback_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "execution": self.execution.to_dict(),
            "record_id": self.record_id,
            "feedback_context": self.feedback_context,
            "live_trading": False,
        }


class F6PaperLoop:
    """
    OBSERVE → ANALYZE → REGIME → SIGNAL → RISK → DECISION → PAPER → RESULT → FEEDBACK
    LIVE broker path is intentionally absent.
    """

    def __init__(
        self,
        *,
        feedback: DecisionFeedbackLoop | None = None,
        replay: DecisionReplayStore | None = None,
        limits: RiskLimits | None = None,
        strategy: str = "ensemble",
    ) -> None:
        self.feedback = feedback or DecisionFeedbackLoop()
        self.replay = replay or DecisionReplayStore()
        self.limits = limits or RiskLimits()
        self.strategy = strategy

    def run_cycle(
        self,
        *,
        provider: Any,
        ledger: Any | None,
        symbol: str,
        requested_size: float = 10.0,
        simulated_exit_pnl: Optional[float] = None,
    ) -> F6CycleResult:
        state = observe_market(provider=provider, ledger=ledger, symbol=symbol)
        regime_name = (
            str(state.regime.regime.value)
            if state.regime.regime.known()
            else "UNKNOWN"
        )
        ctx = self.feedback.next_decision_context(self.strategy, regime_name)
        size_mult = float(ctx.get("size_multiplier") or 1.0)
        effective_size = requested_size * size_mult

        decision = decide_from_state(
            state,
            requested_size=effective_size,
            limits=self.limits,
            consecutive_losses=int(ctx.get("consecutive_losses") or 0),
            daily_pnl=float(ctx.get("daily_pnl") or 0.0),
            calibration_hint=ctx.get("calibration_hint"),
            strategy_memory_hint=ctx.get("strategy_memory_hint"),
        )

        if decision.decision == DecisionAction.NO_TRADE or effective_size <= 0:
            if effective_size <= 0 and decision.decision != DecisionAction.NO_TRADE:
                # Force NO_TRADE when memory size multiplier is zero
                decision.decision = DecisionAction.NO_TRADE
                decision.position_size = 0.0
                decision.reason = "strategy_memory_size_zero"
                decision.no_trade_reasons = list(decision.no_trade_reasons) + ["strategy_memory"]
            self.feedback.record_no_trade(decision.to_dict())
            execution = PaperExecutionResult(
                executed=False,
                quantity=0.0,
                note="NO_TRADE_RECORDED",
            )
            rec = self.replay.save_from_decision(decision.to_dict(), execution=execution.to_dict())
            return F6CycleResult(
                decision=decision,
                execution=execution,
                record_id=rec.record_id,
                feedback_context=ctx,
            )

        # Paper "execution" — no broker, optional simulated PnL for feedback tests
        price = float(state.price.last.value) if state.price.last.known() else None
        execution = PaperExecutionResult(
            executed=True,
            fill_price=price,
            quantity=decision.position_size,
            pnl=float(simulated_exit_pnl or 0.0),
            note="PAPER_FILL_SIMULATED",
        )
        rec = self.replay.save_from_decision(decision.to_dict(), execution=execution.to_dict())

        if simulated_exit_pnl is not None:
            result = self.feedback.record_result(
                symbol=symbol,
                decision=decision.decision.value,
                confidence=decision.confidence,
                pnl=float(simulated_exit_pnl),
                regime=regime_name,
                strategy=self.strategy,
                signal_type=str((decision.composite_signal or {}).get("direction") or "COMPOSITE"),
            )
            self.replay.attach_result(
                rec.record_id,
                {"pnl": simulated_exit_pnl, "lesson": result.lesson, "won": result.won},
            )

        return F6CycleResult(
            decision=decision,
            execution=execution,
            record_id=rec.record_id,
            feedback_context=self.feedback.next_decision_context(self.strategy, regime_name),
        )
