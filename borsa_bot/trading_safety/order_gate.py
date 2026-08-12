"""Central pre-submit safety gate — unknown = blocked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_safety.circuit_breaker import CircuitBreaker
from trading_safety.kill_switch import KillSwitch
from trading_safety.micro_live import MicroLiveLimits
from trading_safety.modes import TradingExecutionMode
from trading_safety.unknown_order import UnknownOrderRegistry


@dataclass
class GateContext:
    mode: TradingExecutionMode
    symbol: str
    side: str
    quantity: float
    price: float
    signal: str = ""
    # Market data
    data_present: bool = False
    data_fresh: bool = False
    price_valid: bool = False
    symbol_valid: bool = False
    market_open: bool | None = None  # None = unknown → block for live-ish modes
    provider_healthy: bool = False
    provider_kind: str = "UNKNOWN"
    # Signal
    signal_valid: bool = False
    signal_fresh: bool = False
    confidence_ok: bool = False
    strategy_consistent: bool = False
    # Portfolio
    positions_known: bool = False
    cash_known: bool = False
    exposure_ok: bool = False
    concentration_ok: bool = False
    duplicate_position: bool = False
    # Risk
    max_order_ok: bool = False
    max_position_ok: bool = False
    daily_loss_ok: bool = False
    max_exposure_ok: bool = False
    max_trades_ok: bool = False
    cooldown_ok: bool = True
    volatility_ok: bool = True
    # System
    broker_state_known: bool = False
    order_status_known: bool = True
    config_complete: bool = False
    persistence_ok: bool = False
    audit_ok: bool = False
    clock_ok: bool = True
    reconciliation_ok: bool = True
    live_broker_enabled: bool = False
    live_confirmed: bool = False
    trades_today: int = 0
    daily_loss_pct: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateDecision:
    allowed: bool
    reason: str
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "checks": self.checks}


def _block(reason: str, checks: list[str]) -> GateDecision:
    return GateDecision(False, reason, checks)


def evaluate_order_gate(
    ctx: GateContext,
    *,
    kill: KillSwitch | None = None,
    breaker: CircuitBreaker | None = None,
    unknowns: UnknownOrderRegistry | None = None,
    micro_limits: MicroLiveLimits | None = None,
) -> GateDecision:
    checks: list[str] = []

    if kill is not None:
        blocked, reason = kill.blocks_new_orders()
        checks.append("kill_switch")
        if blocked:
            return _block(reason, checks)

    if breaker is not None:
        blocked, reason = breaker.blocks_new_orders()
        checks.append("circuit_breaker")
        if blocked:
            return _block(reason, checks)

    if unknowns is not None:
        blocked, reason = unknowns.has_blocking_unknown(ctx.symbol)
        checks.append("unknown_orders")
        if blocked:
            return _block(reason, checks)

    if not ctx.reconciliation_ok:
        return _block("RECONCILIATION_REQUIRED", checks + ["reconciliation"])

    if not ctx.config_complete:
        return _block("MISSING_CONFIGURATION", checks + ["config"])
    if not ctx.clock_ok:
        return _block("CLOCK_INCONSISTENCY", checks + ["clock"])
    if not ctx.persistence_ok:
        return _block("PERSISTENCE_FAILURE", checks + ["persistence"])
    if not ctx.audit_ok:
        return _block("AUDIT_FAILURE", checks + ["audit"])

    # Market data — unknown/stale/missing = block
    for name, ok in (
        ("data_present", ctx.data_present),
        ("data_fresh", ctx.data_fresh),
        ("price_valid", ctx.price_valid),
        ("symbol_valid", ctx.symbol_valid),
        ("provider_healthy", ctx.provider_healthy),
    ):
        checks.append(name)
        if not ok:
            return _block(f"MD_{name.upper()}_FAILED", checks)

    kind = (ctx.provider_kind or "UNKNOWN").upper()
    checks.append("provider_kind")
    if kind in {"REQUIRED", "UNKNOWN", "UNAVAILABLE", "SIMULATED", "TEST", "MISSING", ""}:
        # PAPER may use SIMULATED; SHADOW may observe simulated; never for MICRO/LIVE
        if ctx.mode in {TradingExecutionMode.MICRO_LIVE, TradingExecutionMode.LIVE}:
            return _block(f"UNRELIABLE_PROVIDER_KIND:{kind}", checks)
        if kind in {"REQUIRED", "UNKNOWN", "UNAVAILABLE", "MISSING", ""}:
            return _block(f"UNRELIABLE_PROVIDER_KIND:{kind}", checks)

    if ctx.mode in {TradingExecutionMode.MICRO_LIVE, TradingExecutionMode.LIVE}:
        if ctx.market_open is None:
            return _block("MARKET_STATE_UNKNOWN", checks + ["market_open"])
        if ctx.market_open is False:
            return _block("MARKET_CLOSED", checks + ["market_open"])

    # Signal
    for name, ok in (
        ("signal_valid", ctx.signal_valid),
        ("signal_fresh", ctx.signal_fresh),
        ("confidence_ok", ctx.confidence_ok),
        ("strategy_consistent", ctx.strategy_consistent),
    ):
        checks.append(name)
        if not ok:
            return _block(f"SIGNAL_{name.upper()}_FAILED", checks)

    # Portfolio
    for name, ok in (
        ("positions_known", ctx.positions_known),
        ("cash_known", ctx.cash_known),
        ("exposure_ok", ctx.exposure_ok),
        ("concentration_ok", ctx.concentration_ok),
    ):
        checks.append(name)
        if not ok:
            return _block(f"PORTFOLIO_{name.upper()}_FAILED", checks)
    if ctx.duplicate_position and ctx.side.upper() == "BUY":
        return _block("DUPLICATE_POSITION", checks + ["duplicate_position"])

    # Risk
    for name, ok in (
        ("max_order_ok", ctx.max_order_ok),
        ("max_position_ok", ctx.max_position_ok),
        ("daily_loss_ok", ctx.daily_loss_ok),
        ("max_exposure_ok", ctx.max_exposure_ok),
        ("max_trades_ok", ctx.max_trades_ok),
        ("cooldown_ok", ctx.cooldown_ok),
        ("volatility_ok", ctx.volatility_ok),
    ):
        checks.append(name)
        if not ok:
            return _block(f"RISK_{name.upper()}_FAILED", checks)

    if not ctx.order_status_known:
        return _block("ORDER_STATUS_UNKNOWN", checks + ["order_status"])

    # Mode-specific broker rules
    if ctx.mode is TradingExecutionMode.SHADOW:
        checks.append("shadow_no_broker")
        return GateDecision(True, "SHADOW_WOULD", checks)

    if ctx.mode is TradingExecutionMode.PAPER:
        checks.append("paper_ok")
        return GateDecision(True, "PAPER_OK", checks)

    # MICRO_LIVE / LIVE
    if not ctx.broker_state_known:
        return _block("BROKER_STATE_UNKNOWN", checks + ["broker_state"])
    if not ctx.live_broker_enabled:
        return _block("LIVE_BROKER_ENABLED=false", checks + ["live_flag"])
    if not ctx.live_confirmed:
        return _block("LIVE_CONFIRMATION_REQUIRED", checks + ["live_confirm"])

    if ctx.mode is TradingExecutionMode.MICRO_LIVE:
        limits = micro_limits or MicroLiveLimits()
        ok, reason = limits.check_order(
            symbol=ctx.symbol,
            qty=ctx.quantity,
            price=ctx.price,
            trades_today=ctx.trades_today,
            daily_loss_pct=ctx.daily_loss_pct,
        )
        checks.append("micro_live_limits")
        if not ok:
            return _block(reason, checks)

    if ctx.mode is TradingExecutionMode.LIVE:
        # Full live still blocked at pipeline unless explicitly allowed — gate alone is not unlock
        checks.append("live_mode_requires_explicit_pipeline_policy")
        return _block("LIVE_MODE_NOT_AUTO_ENABLED", checks)

    return GateDecision(True, "OK", checks)


def paper_ready_context(**overrides: Any) -> GateContext:
    """Baseline fail-closed-ok context for PAPER unit tests."""
    base = GateContext(
        mode=TradingExecutionMode.PAPER,
        symbol="THYAO",
        side="BUY",
        quantity=1.0,
        price=100.0,
        signal="AL",
        data_present=True,
        data_fresh=True,
        price_valid=True,
        symbol_valid=True,
        market_open=True,
        provider_healthy=True,
        provider_kind="SIMULATED",
        signal_valid=True,
        signal_fresh=True,
        confidence_ok=True,
        strategy_consistent=True,
        positions_known=True,
        cash_known=True,
        exposure_ok=True,
        concentration_ok=True,
        duplicate_position=False,
        max_order_ok=True,
        max_position_ok=True,
        daily_loss_ok=True,
        max_exposure_ok=True,
        max_trades_ok=True,
        cooldown_ok=True,
        volatility_ok=True,
        broker_state_known=True,
        order_status_known=True,
        config_complete=True,
        persistence_ok=True,
        audit_ok=True,
        clock_ok=True,
        reconciliation_ok=True,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base
