"""Safe execution pipeline — single entry for paper/shadow/(blocked) micro-live."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from config.models import OrderRequest, OrderResult
from config.settings import settings
from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled
from execution.paper import PaperBroker
from portfolio.ledger import PortfolioLedger
from trading_safety.audit import TradingAuditLog, new_audit
from trading_safety.circuit_breaker import CircuitBreaker
from trading_safety.idempotency import IdempotencyStore
from trading_safety.kill_switch import KillSwitch
from trading_safety.metrics import TradingMetrics
from trading_safety.micro_live import MicroLiveLimits
from trading_safety.modes import TradingExecutionMode
from trading_safety.order_gate import GateContext, evaluate_order_gate
from trading_safety.unknown_order import UnknownOrderRegistry


@dataclass
class SafeSubmitResult:
    ok: bool
    status: str
    message: str
    order_result: OrderResult | None = None
    gate_reason: str = ""
    idempotency_key: str = ""
    mode: str = "PAPER"
    would_submit: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.order_result is not None:
            d["order_result"] = {
                "ok": self.order_result.ok,
                "status": self.order_result.status,
                "message": self.order_result.message,
                "order_id": self.order_result.order_id,
            }
        return d


class SafeExecutionPipeline:
    """Fail-closed submit path. PAPER fills paper broker; SHADOW never submits; LIVE blocked."""

    def __init__(
        self,
        *,
        paper: PaperBroker | None = None,
        router: ExecutionRouter | None = None,
        mode: TradingExecutionMode = TradingExecutionMode.PAPER,
        kill: KillSwitch | None = None,
        breaker: CircuitBreaker | None = None,
        idem: IdempotencyStore | None = None,
        audit: TradingAuditLog | None = None,
        metrics: TradingMetrics | None = None,
        unknowns: UnknownOrderRegistry | None = None,
        micro_limits: MicroLiveLimits | None = None,
        db_dir: Path | None = None,
    ) -> None:
        base = db_dir or (Path(__file__).resolve().parents[1] / "logs")
        if paper is None:
            ledger = PortfolioLedger(db_path=base / "paper_ledger.db")
            paper = PaperBroker(ledger)
        self.paper = paper
        self.router = router or ExecutionRouter(paper=self.paper, live=LiveBrokerDisabled())
        # Prefer factory-resolved adapter when caller did not inject a router
        if router is None:
            from execution.live_factory import resolve_live_adapter

            self.router = ExecutionRouter(paper=self.paper, live=resolve_live_adapter())
        self.mode = mode
        self.kill = kill or KillSwitch(active=bool(getattr(settings, "kill_switch", False)), reason="settings", source="configuration")
        if getattr(settings, "kill_switch", False) and not self.kill.active:
            self.kill.activate("KILL_SWITCH settings", source="configuration")
        self.breaker = breaker or CircuitBreaker()
        self.idem = idem or IdempotencyStore(base / "idempotency.db")
        self.audit = audit or TradingAuditLog(base / "trading_audit.db")
        self.metrics = metrics or TradingMetrics()
        self.unknowns = unknowns or UnknownOrderRegistry()
        self.micro_limits = micro_limits or MicroLiveLimits()
        # Simulate broker timeout callback for tests
        self._force_unknown_on_submit: bool = False

    def sync_kill_from_settings(self) -> None:
        if bool(getattr(settings, "kill_switch", False)):
            if not self.kill.active:
                self.kill.activate("KILL_SWITCH settings", source="configuration")
                self.metrics.kill_switch_events += 1

    def submit(
        self,
        order: OrderRequest,
        sector: str,
        *,
        ctx: GateContext,
        cycle_id: str = "cycle",
        signal: str = "",
        strategy_decision: str = "",
        risk_decision: str = "",
        provider_state: str = "",
        portfolio_state: str = "",
        market_data_timestamp: str | None = None,
        simulate_broker_timeout: bool = False,
    ) -> SafeSubmitResult:
        t0 = time.perf_counter()
        self.sync_kill_from_settings()
        mode = ctx.mode
        self.mode = mode

        # Idempotency
        key = order.client_order_id or self.idem.make_key(
            symbol=order.symbol,
            side=order.side,
            signal=signal or ctx.signal or "NA",
            cycle_id=cycle_id,
            window_bucket=int(time.time() // 900),
        )
        if not order.client_order_id:
            order.client_order_id = key
        claim = self.idem.claim(key, symbol=order.symbol, side=order.side)
        if claim.duplicate:
            self.metrics.record_duplicate()
            self.metrics.record_reject()
            return SafeSubmitResult(
                False,
                "DUPLICATE",
                "idempotency key already claimed — NO ORDER",
                idempotency_key=key,
                mode=mode.value,
                gate_reason="DUPLICATE_ORDER",
            )

        # Audit must succeed before any broker-touching path
        rec = new_audit(
            symbol=order.symbol,
            signal=signal or ctx.signal,
            strategy_decision=strategy_decision or "N/A",
            risk_decision=risk_decision or "N/A",
            provider_state=provider_state or ctx.provider_kind,
            portfolio_state=portfolio_state or "N/A",
            order_intent=f"{order.side} {order.quantity}@{order.price}",
            idempotency_key=key,
            mode=mode.value,
            market_data_timestamp=market_data_timestamp,
        )
        audit_ok = self.audit.append(rec)
        ctx.audit_ok = audit_ok
        ctx.persistence_ok = audit_ok
        if mode is TradingExecutionMode.PAPER and not ctx.config_complete:
            ctx.config_complete = True

        decision = evaluate_order_gate(
            ctx,
            kill=self.kill,
            breaker=self.breaker,
            unknowns=self.unknowns,
            micro_limits=self.micro_limits,
        )
        if not decision.allowed:
            self.metrics.record_reject()
            self.idem.mark_status(key, f"BLOCKED:{decision.reason}")
            if "CIRCUIT" in decision.reason:
                self.metrics.circuit_breaker_events += 1
            if "KILL" in decision.reason:
                self.metrics.kill_switch_events += 1
            return SafeSubmitResult(
                False,
                "BLOCKED",
                decision.reason,
                idempotency_key=key,
                mode=mode.value,
                gate_reason=decision.reason,
                details={"checks": decision.checks},
            )

        if not audit_ok:
            self.metrics.record_reject()
            return SafeSubmitResult(
                False,
                "BLOCKED",
                "AUDIT_FAILURE",
                idempotency_key=key,
                mode=mode.value,
                gate_reason="AUDIT_FAILURE",
            )

        # SHADOW — never send
        if mode is TradingExecutionMode.SHADOW:
            self.metrics.order_success += 1
            self.idem.mark_status(key, "SHADOW")
            return SafeSubmitResult(
                True,
                "SHADOW",
                "WOULD submit — no real order",
                idempotency_key=key,
                mode=mode.value,
                would_submit=True,
                order_result=OrderResult(True, None, "SHADOW", "would", order.price, order.quantity, {"would": True}),
            )

        # LIVE / MICRO_LIVE real broker — still hard-blocked unless flags (and LIVE mode blocked in gate)
        if mode is TradingExecutionMode.LIVE:
            self.metrics.record_reject()
            return SafeSubmitResult(
                False,
                "BLOCKED",
                "LIVE_MODE_NOT_AUTO_ENABLED",
                idempotency_key=key,
                mode=mode.value,
                gate_reason="LIVE_MODE_NOT_AUTO_ENABLED",
            )

        if mode is TradingExecutionMode.MICRO_LIVE:
            # Even MICRO_LIVE does not auto-send without unlock; if unlocked, still go through router LIVE path
            if not bool(getattr(settings, "live_broker_enabled", False)):
                self.metrics.record_reject()
                return SafeSubmitResult(
                    False,
                    "BLOCKED",
                    "MICRO_LIVE requires LIVE_BROKER_ENABLED (human) — currently false",
                    idempotency_key=key,
                    mode=mode.value,
                    gate_reason="MICRO_LIVE_LOCKED",
                )
            # Intentionally still do not auto-confirm live_money_readiness
            self.metrics.record_reject()
            return SafeSubmitResult(
                False,
                "BLOCKED",
                "MICRO_LIVE readiness NOT VERIFIED — safety layer present, live-money not enabled",
                idempotency_key=key,
                mode=mode.value,
                gate_reason="LIVE_MONEY_READINESS_NOT_VERIFIED",
            )

        # PAPER
        if simulate_broker_timeout or self._force_unknown_on_submit:
            self.unknowns.mark_unknown(key, symbol=order.symbol, side=order.side, quantity=order.quantity)
            self.metrics.unknown_order_events += 1
            self.idem.mark_status(key, "UNKNOWN")
            self.breaker.record_failure("UNKNOWN_ORDER")
            return SafeSubmitResult(
                False,
                "UNKNOWN",
                "broker response lost — NOT assumed failed",
                idempotency_key=key,
                mode=mode.value,
                gate_reason="UNKNOWN_ORDER",
            )

        result = self.router.submit(order, sector, execution_mode="PAPER")
        self.metrics.execution_latency_ms.append((time.perf_counter() - t0) * 1000)
        if result.ok:
            self.metrics.order_success += 1
            self.idem.mark_status(key, result.status, result.order_id)
        else:
            self.metrics.order_failure += 1
            self.idem.mark_status(key, result.status or "FAILED", result.order_id)
            self.breaker.record_failure("EXECUTION_FAILURE")
        return SafeSubmitResult(
            bool(result.ok),
            result.status,
            result.message,
            order_result=result,
            idempotency_key=key,
            mode=mode.value,
        )
