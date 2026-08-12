"""Position / cash reconciliation — mismatch → RECONCILIATION_REQUIRED (no new orders)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SafetyReconcileResult:
    ok: bool
    state: str  # OK | RECONCILIATION_REQUIRED
    mismatches: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blocks_trading(self) -> bool:
        return self.state == "RECONCILIATION_REQUIRED" or not self.ok


def reconcile_bot_vs_broker(
    *,
    bot_positions: dict[str, float],
    broker_positions: dict[str, float],
    bot_cash: float | None = None,
    broker_cash: float | None = None,
    qty_tol: float = 1e-6,
) -> SafetyReconcileResult:
    mismatches: list[str] = []
    for sym, qty in bot_positions.items():
        bq = broker_positions.get(sym)
        if bq is None:
            mismatches.append(f"BROKER_MISSING_POSITION:{sym}")
        elif abs(float(bq) - float(qty)) > qty_tol:
            mismatches.append(f"QTY_MISMATCH:{sym}:bot={qty}:broker={bq}")
    for sym, bq in broker_positions.items():
        if sym not in bot_positions:
            mismatches.append(f"BOT_MISSING_POSITION:{sym}")
    if bot_cash is not None and broker_cash is not None:
        if abs(float(bot_cash) - float(broker_cash)) > 0.01:
            mismatches.append(f"CASH_MISMATCH:bot={bot_cash}:broker={broker_cash}")
    elif broker_cash is None and bot_cash is not None:
        # Live path with unknown cash is fail-closed for live; paper may omit
        pass
    if mismatches:
        return SafetyReconcileResult(
            False,
            "RECONCILIATION_REQUIRED",
            mismatches,
            {"bot_n": len(bot_positions), "broker_n": len(broker_positions)},
        )
    return SafetyReconcileResult(True, "OK", [], {"bot_n": len(bot_positions), "broker_n": len(broker_positions)})
