"""Reconciliation — bot ledger vs broker. Paper: self-consistency only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ReconcileResult:
    ok: bool
    halted: bool
    mismatches: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile_paper(trading: Any) -> ReconcileResult:
    """Paper path: verify positions table vs in-memory marks; cash non-negative."""
    mismatches: list[str] = []
    try:
        cash = float(trading.ledger.cash)
        if cash < -1e-6:
            mismatches.append("NEGATIVE_CASH")
        for pos in trading.ledger.positions():
            if pos.quantity <= 0:
                mismatches.append(f"INVALID_QTY:{pos.symbol}")
            if pos.avg_cost <= 0:
                mismatches.append(f"INVALID_AVG_COST:{pos.symbol}")
        return ReconcileResult(
            ok=not mismatches,
            halted=bool(mismatches),
            mismatches=mismatches,
            details={"venue": "PAPER", "positions": trading.ledger.open_position_count()},
        )
    except Exception as exc:  # noqa: BLE001
        return ReconcileResult(False, True, [f"RECONCILE_ERROR:{exc}"], {})


def reconcile_live(trading: Any, broker: Any) -> ReconcileResult:
    """Compare ledger positions to broker positions — mismatch HALTS trading."""
    mismatches: list[str] = []
    try:
        broker_pos = {p.get("symbol"): p for p in (broker.positions() or []) if p.get("symbol")}
        local = {p.symbol: p for p in trading.ledger.positions()}
        for sym, pos in local.items():
            bp = broker_pos.get(sym)
            if bp is None:
                mismatches.append(f"BROKER_MISSING_POSITION:{sym}")
                continue
            bq = float(bp.get("quantity") or 0)
            if abs(bq - float(pos.quantity)) > 1e-6:
                mismatches.append(f"QTY_MISMATCH:{sym}:local={pos.quantity}:broker={bq}")
        for sym in broker_pos:
            if sym not in local:
                mismatches.append(f"LOCAL_MISSING_POSITION:{sym}")
        bal = broker.balances() or {}
        if bal.get("available") is None and bool(getattr(trading, "settings", None)):
            mismatches.append("BROKER_BALANCE_UNKNOWN")
        halted = bool(mismatches)
        return ReconcileResult(not halted, halted, mismatches, {"venue": "LIVE", "broker_positions": len(broker_pos)})
    except Exception as exc:  # noqa: BLE001
        return ReconcileResult(False, True, [f"RECONCILE_ERROR:{exc}"], {})
