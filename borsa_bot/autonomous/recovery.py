"""Recovery helpers — reconnect/retry for transient errors; never continue on financial ambiguity."""

from __future__ import annotations

from typing import Any


FINANCIAL_AMBIGUITY = {
    "UNKNOWN_ORDER",
    "POSITION_MISMATCH",
    "BALANCE_MISMATCH",
    "ORDER_STATUS_UNKNOWN",
    "RECONCILE_FAIL",
}


def classify_failure(reason: str) -> str:
    r = (reason or "").upper()
    for key in FINANCIAL_AMBIGUITY:
        if key in r:
            return "HALT"
    if any(x in r for x in ("STALE", "TIMEOUT", "DISCONNECT", "API_DOWN", "NETWORK")):
        return "RETRY"
    if any(x in r for x in ("KILL", "DAILY_LOSS", "DRAWDOWN", "MOCK", "PRODUCTION")):
        return "HALT"
    return "HALT"


def attempt_provider_recover(trading: Any) -> dict[str, Any]:
    """Best-effort tick / freshness refresh — does not fabricate data."""
    try:
        trading.tick()
        meta = trading.provider.source_meta()
        return {
            "ok": bool(trading.provider.has_market_data()),
            "kind": meta.kind.value if hasattr(meta.kind, "value") else str(meta.kind),
            "action": "provider_tick",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "action": "provider_tick"}
