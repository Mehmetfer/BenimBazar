"""Process restart recovery — LOAD → QUERY → RECONCILE → VALIDATE → SAFE → RESUME."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from trading_safety.reconcile import SafetyReconcileResult, reconcile_bot_vs_broker
from trading_safety.unknown_order import UnknownOrderRegistry


@dataclass
class RestartRecoveryResult:
    ok: bool
    may_resume: bool
    steps: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    reconcile: dict[str, Any] = field(default_factory=dict)
    unknown_orders: int = 0
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recover_after_restart(
    *,
    load_state: Callable[[], dict[str, Any]],
    query_broker_positions: Callable[[], dict[str, float]],
    query_broker_cash: Callable[[], float | None] | None = None,
    unknown_registry: UnknownOrderRegistry | None = None,
    risk_validate: Callable[[], tuple[bool, str]] | None = None,
) -> RestartRecoveryResult:
    steps: list[str] = []
    try:
        state = load_state()
        steps.append("LOAD_STATE")
    except Exception as exc:  # noqa: BLE001
        return RestartRecoveryResult(False, False, ["LOAD_STATE_FAILED"], f"STATE_LOAD:{exc}")

    bot_pos = {str(k): float(v) for k, v in (state.get("positions") or {}).items()}
    bot_cash = state.get("cash")
    try:
        broker_pos = query_broker_positions()
        steps.append("QUERY_BROKER")
    except Exception as exc:  # noqa: BLE001
        return RestartRecoveryResult(False, False, steps + ["QUERY_BROKER_FAILED"], f"BROKER_QUERY:{exc}")

    broker_cash = None
    if query_broker_cash is not None:
        try:
            broker_cash = query_broker_cash()
        except Exception:  # noqa: BLE001
            broker_cash = None

    rec = reconcile_bot_vs_broker(
        bot_positions=bot_pos,
        broker_positions=broker_pos,
        bot_cash=float(bot_cash) if bot_cash is not None else None,
        broker_cash=broker_cash,
    )
    steps.append("RECONCILE")
    if rec.blocks_trading:
        return RestartRecoveryResult(
            False,
            False,
            steps,
            "RECONCILIATION_REQUIRED",
            reconcile=rec.to_dict(),
        )

    unknowns = unknown_registry.open_unknowns() if unknown_registry else []
    steps.append("CHECK_UNKNOWN_ORDERS")
    if unknowns:
        return RestartRecoveryResult(
            False,
            False,
            steps,
            f"UNKNOWN_ORDERS:{len(unknowns)}",
            reconcile=rec.to_dict(),
            unknown_orders=len(unknowns),
        )

    if risk_validate is not None:
        ok, reason = risk_validate()
        steps.append("VALIDATE_RISK")
        if not ok:
            return RestartRecoveryResult(False, False, steps, f"RISK:{reason}", reconcile=rec.to_dict())

    steps.append("RESTORE_SAFE_STATE")
    steps.append("RESUME_ALLOWED")
    return RestartRecoveryResult(True, True, steps, "", reconcile=rec.to_dict(), unknown_orders=0)
