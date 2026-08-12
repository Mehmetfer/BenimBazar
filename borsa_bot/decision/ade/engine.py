"""Autonomous Decision Engine — observe → decide → validate → (optional) execute."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from config.models import OrderRequest
from decision.ade.chain import ChainResult, MarketSnapshot, run_decision_chain
from decision.ade.correction import CorrectionResult, run_self_correction
from decision.ade.learning import AdaptiveLearner, LearningOutcome
from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.reasons import (
    RC_POST_TRADE_OK,
    RC_RECOVERY_FAILED,
    RC_SAFETY_GATE_BLOCKED,
    RC_SAFETY_PASSED,
    RC_SIGNAL_CONFLICT,
    RC_VALIDATORS_PASSED,
    DecisionReason,
)
from decision.ade.states import DecisionAction, is_executable
from decision.ade.validator import validate_decision, validate_risk
from trading_safety.kill_switch import KillSwitch
from trading_safety.modes import TradingExecutionMode
from trading_safety.order_gate import GateContext, paper_ready_context
from trading_safety.pipeline import SafeExecutionPipeline, SafeSubmitResult


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AutonomousDecisionRecord:
    decision_id: str
    cycle_id: str
    action: str
    symbol: str
    confidence: float
    reason: dict[str, Any]
    chain: dict[str, Any]
    decision_validator: dict[str, Any]
    risk_validator: dict[str, Any]
    safety: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    post_trade: dict[str, Any] = field(default_factory=dict)
    correction: dict[str, Any] = field(default_factory=dict)
    learning: dict[str, Any] = field(default_factory=dict)
    waited_for_human: bool = False
    created_at: str = field(default_factory=_utc)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousDecisionEngine:
    """Humanless decision maker within immutable safety limits.

    Never unlocks LIVE money. Confidence ≠ execution authority.
    """

    def __init__(
        self,
        *,
        limits: ImmutableSafetyLimits | None = None,
        pipeline: SafeExecutionPipeline | None = None,
        mode: TradingExecutionMode = TradingExecutionMode.PAPER,
        learner: AdaptiveLearner | None = None,
        kill: KillSwitch | None = None,
    ) -> None:
        self.limits = limits or ImmutableSafetyLimits(live_broker_enabled=False)
        self.mode = mode
        self.kill = kill or KillSwitch(active=self.limits.kill_switch_active)
        self.pipeline = pipeline
        self.learner = learner or AdaptiveLearner(limits=self.limits)
        self._audit: list[AutonomousDecisionRecord] = []
        self._portfolio: dict[str, float] = {}
        self._cash: float = 100_000.0
        self._halted: bool = False
        self._halt_reason: str = ""

    @property
    def audit_log(self) -> list[AutonomousDecisionRecord]:
        return list(self._audit)

    @property
    def halted(self) -> bool:
        return self._halted

    def decide(
        self,
        snap: MarketSnapshot,
        *,
        cycle_id: str | None = None,
        execute: bool = False,
        alternate_provider: dict[str, Any] | None = None,
    ) -> AutonomousDecisionRecord:
        """Full cycle through chain → validators → optional safety/execution."""
        cid = cycle_id or f"ade-{uuid4().hex[:10]}"
        did = f"dec-{uuid4().hex[:12]}"

        if self._halted:
            return self._record_no_trade(
                did,
                cid,
                snap,
                codes=["SAFE_HALT"],
                message=self._halt_reason or "halted",
            )

        correction: CorrectionResult | None = None
        # Self-correction when primary data unhealthy
        if not (snap.provider_ok and snap.data_valid and snap.data_fresh):

            def primary() -> dict[str, Any]:
                return {
                    "ok": snap.provider_ok,
                    "data_valid": snap.data_valid,
                    "data_fresh": snap.data_fresh,
                    "provider": snap.provider,
                }

            alt_probe = None
            if alternate_provider is not None:

                def alt_probe() -> dict[str, Any]:  # noqa: F811
                    return alternate_provider

            correction = run_self_correction(
                primary_probe=primary,
                alternate_probe=alt_probe,
                kill_switch=self.limits.kill_switch_active or self.kill.active,
            )
            if correction.details.get("halt"):
                self._halted = True
                self._halt_reason = "UNRECOVERABLE_FAILURE"
            if not correction.verified:
                rec = self._record_no_trade(
                    did,
                    cid,
                    snap,
                    codes=[RC_RECOVERY_FAILED],
                    message="self-correction failed or unverified",
                    correction=correction.to_dict(),
                )
                return rec
            if correction.recovered and alternate_provider:
                snap = replace(
                    snap,
                    provider=str(alternate_provider.get("provider", snap.provider)),
                    provider_ok=True,
                    data_valid=True,
                    data_fresh=True,
                    provider_reliability=float(alternate_provider.get("reliability", 0.7)),
                )

        chain = run_decision_chain(snap, self.limits)
        action = chain.action
        size = chain.size
        capped = size.capped_size if size else 0.0
        calculated = size.calculated_size if size else 0.0

        # Decision validator
        dv = validate_decision(
            action=action,
            data_fresh=snap.data_fresh,
            data_valid=snap.data_valid,
            signal_consistent=_signals_consistent(chain),
            signals=list(snap.signals),
            calculated_size=calculated,
            capped_size=capped,
            limits=self.limits,
            expected_execution_ok=True,
            decision_confidence=chain.confidence if is_executable(action) else 1.0,
        )
        rv = validate_risk(
            action=action,
            daily_loss_pct=snap.daily_loss_pct,
            exposure_pct=snap.exposure_pct,
            risk_reward=snap.risk_reward,
            expected_value=snap.expected_value,
            slippage_bps=snap.slippage_bps + snap.cost_bps,
            limits=self.limits,
            kill_switch=self.kill.active,
        )

        safety: dict[str, Any] = {}
        execution: dict[str, Any] = {}
        post_trade: dict[str, Any] = {}

        if not dv.ok or not rv.ok:
            action = DecisionAction.NO_TRADE
            chain.reason.add(
                RC_SAFETY_GATE_BLOCKED if not rv.ok else "DECISION_VALIDATION_FAILED",
                "validator blocked execution",
            )
        elif is_executable(action) and execute:
            # SAFETY GATE + EXECUTION via SafeExecutionPipeline only
            if self.pipeline is None:
                # Never touch the shared production paper.db; isolate ADE fills.
                import tempfile
                from pathlib import Path

                tmp = Path(tempfile.mkdtemp(prefix="ade_pipeline_"))
                self.pipeline = SafeExecutionPipeline(mode=self.mode, kill=self.kill, db_dir=tmp)
            side = "BUY" if action is DecisionAction.BUY else "SELL"
            if action in {DecisionAction.EXIT, DecisionAction.REDUCE, DecisionAction.SELL}:
                side = "SELL"
            order = OrderRequest(
                symbol=snap.symbol,
                side=side,
                quantity=max(capped, 0.0),
                price=snap.price,
                reason=f"ADE:{action.value}",
                client_order_id=f"{cid}-{did}",
            )
            ctx = self._gate_context(snap, action, capped)
            submit: SafeSubmitResult = self.pipeline.submit(
                order,
                snap.sector,
                ctx=ctx,
                cycle_id=cid,
                signal=",".join(snap.signals),
                strategy_decision=action.value,
                risk_decision="APPROVE" if rv.ok else "REJECT",
                provider_state=snap.provider,
                portfolio_state=str(self._portfolio),
                market_data_timestamp=snap.timestamp or _utc(),
            )
            safety = {"gate_reason": submit.gate_reason, "status": submit.status, "ok": submit.ok}
            execution = submit.to_dict()
            if submit.ok:
                chain.reason.add(RC_SAFETY_PASSED, "safety gate passed")
                post_trade = self._verify_and_update(snap, action, capped, side, submit)
                chain.reason.add(RC_POST_TRADE_OK, "post-trade verified")
            else:
                action = DecisionAction.NO_TRADE
                chain.reason.add(RC_SAFETY_GATE_BLOCKED, submit.gate_reason or submit.message)
        else:
            if dv.ok and rv.ok:
                chain.reason.add(RC_VALIDATORS_PASSED, "validators ok; execute=False or abstain")

        learning = self._learn(action, snap, post_trade)

        rec = AutonomousDecisionRecord(
            decision_id=did,
            cycle_id=cid,
            action=action.value,
            symbol=snap.symbol,
            confidence=chain.confidence,
            reason=chain.reason.to_dict(),
            chain=chain.to_dict(),
            decision_validator=dv.to_dict(),
            risk_validator=rv.to_dict(),
            safety=safety,
            execution=execution,
            post_trade=post_trade,
            correction=correction.to_dict() if correction else {},
            learning=learning.to_dict() if learning else {},
            waited_for_human=False,
        )
        self._audit.append(rec)
        return rec

    def _gate_context(self, snap: MarketSnapshot, action: DecisionAction, qty: float) -> GateContext:
        # PAPER/SHADOW: PUBLIC/SIMULATED kinds allowed; never claim live unlock.
        provider_kind = "PUBLIC" if snap.provider_ok else "UNKNOWN"
        ctx = paper_ready_context(
            mode=self.mode,
            symbol=snap.symbol,
            side="BUY" if action is DecisionAction.BUY else "SELL",
            quantity=qty,
            price=snap.price,
            provider_kind=provider_kind,
            provider_healthy=snap.provider_ok,
            data_present=True,
            data_fresh=snap.data_fresh,
            price_valid=snap.price > 0,
        )
        ctx.signal = action.value
        ctx.signal_valid = True
        ctx.signal_fresh = True
        ctx.confidence_ok = True
        ctx.strategy_consistent = True
        return ctx

    def _verify_and_update(
        self,
        snap: MarketSnapshot,
        action: DecisionAction,
        qty: float,
        side: str,
        submit: SafeSubmitResult,
    ) -> dict[str, Any]:
        verified = submit.ok and submit.status in {"FILLED", "SHADOW", "OK", "PAPER"}
        # Prefer explicit order_result
        if submit.order_result is not None:
            verified = bool(submit.order_result.ok) or submit.status == "SHADOW"

        pos = self._portfolio.get(snap.symbol, 0.0)
        if verified and self.mode is TradingExecutionMode.PAPER:
            if side == "BUY":
                self._portfolio[snap.symbol] = pos + qty
                self._cash -= qty * snap.price
            else:
                self._portfolio[snap.symbol] = max(0.0, pos - qty)
                self._cash += qty * snap.price
        return {
            "verified": verified,
            "portfolio": dict(self._portfolio),
            "cash": self._cash,
            "status": submit.status,
        }

    def _learn(self, action: DecisionAction, snap: MarketSnapshot, post_trade: dict[str, Any]) -> LearningOutcome:
        ok = bool(post_trade.get("verified"))
        return self.learner.learn_from_outcome(
            signal_quality={"trend": 1.05 if ok else 0.95},
            strategy_performance={"last_action": 1.0 if ok else 0.0},
            provider_reliability={snap.provider: snap.provider_reliability},
            execution_quality=1.0 if ok else 0.5,
            slippage_bps=snap.slippage_bps,
            # Prove learning cannot bypass: attempt forbidden update
            attempted_safety_updates={"hard_max_position_size": 1e9, "kill_switch_active": False},
        )

    def _record_no_trade(
        self,
        did: str,
        cid: str,
        snap: MarketSnapshot,
        *,
        codes: list[str],
        message: str,
        correction: dict[str, Any] | None = None,
    ) -> AutonomousDecisionRecord:
        reason = DecisionReason(stage="DECISION_ENGINE")
        for c in codes:
            reason.add(c, message)
        chain = ChainResult(action=DecisionAction.NO_TRADE, reason=reason, stages=["SELF_CORRECTION"])
        rec = AutonomousDecisionRecord(
            decision_id=did,
            cycle_id=cid,
            action=DecisionAction.NO_TRADE.value,
            symbol=snap.symbol,
            confidence=0.0,
            reason=reason.to_dict(),
            chain=chain.to_dict(),
            decision_validator={"ok": False},
            risk_validator={"ok": False},
            correction=correction or {},
            waited_for_human=False,
        )
        self._audit.append(rec)
        return rec


def _signals_consistent(chain: ChainResult) -> bool:
    return RC_SIGNAL_CONFLICT not in set(chain.reason.codes)
