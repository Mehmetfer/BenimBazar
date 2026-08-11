"""Central reason-code taxonomy — machine-readable trade explanations (Master V2 §54)."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ReasonCode(str, Enum):
    # Positive / supporting
    TREND_CONFIRMED = "TREND_CONFIRMED"
    MTF_ALIGNMENT = "MTF_ALIGNMENT"
    VOLUME_CONFIRMATION = "VOLUME_CONFIRMATION"
    REGIME_SUPPORT = "REGIME_SUPPORT"
    RISK_ACCEPTABLE = "RISK_ACCEPTABLE"
    EXPECTED_VALUE_POSITIVE = "EXPECTED_VALUE_POSITIVE"
    LIQUIDITY_OK = "LIQUIDITY_OK"
    DATA_FRESH = "DATA_FRESH"
    FAVORITE_PRIORITY = "FAVORITE_PRIORITY"
    # Blocking / negative
    DATA_STALE = "DATA_STALE"
    DATA_ANOMALY = "DATA_ANOMALY"
    DATA_MOCK_BLOCKED = "DATA_MOCK_BLOCKED"
    REGIME_CONFLICT = "REGIME_CONFLICT"
    MTF_CONFLICT = "MTF_CONFLICT"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    RISK_REJECTED = "RISK_REJECTED"
    NEGATIVE_EV = "NEGATIVE_EV"
    DUPLICATE_POSITION = "DUPLICATE_POSITION"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    MARKET_CLOSED = "MARKET_CLOSED"
    KILL_SWITCH = "KILL_SWITCH"
    RATE_LIMIT = "RATE_LIMIT"
    LOSS_GOVERNOR = "LOSS_GOVERNOR"
    DRAWDOWN_GOVERNOR = "DRAWDOWN_GOVERNOR"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    LIVE_LOCKED = "LIVE_LOCKED"
    MISSING_TRADE_PLAN = "MISSING_TRADE_PLAN"
    MARTINGALE_BLOCKED = "MARTINGALE_BLOCKED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def reasons_from_gate(gate_name: str, reason: str) -> list[str]:
    r = (reason or "").upper()
    mapping = {
        "STALE": ReasonCode.DATA_STALE,
        "MOCK": ReasonCode.DATA_MOCK_BLOCKED,
        "ANOMALY": ReasonCode.DATA_ANOMALY,
        "KILL": ReasonCode.KILL_SWITCH,
        "DUPLICATE": ReasonCode.DUPLICATE_POSITION,
        "MARKET_CLOSED": ReasonCode.MARKET_CLOSED,
        "EXPIRED": ReasonCode.SIGNAL_EXPIRED,
        "EV": ReasonCode.NEGATIVE_EV,
        "TRADE_PLAN": ReasonCode.MISSING_TRADE_PLAN,
        "RATE": ReasonCode.RATE_LIMIT,
        "DRAWDOWN": ReasonCode.DRAWDOWN_GOVERNOR,
        "DAILY_LOSS": ReasonCode.LOSS_GOVERNOR,
        "RECONCILE": ReasonCode.RECONCILE_REQUIRED,
        "LIVE": ReasonCode.LIVE_LOCKED,
        "MTF": ReasonCode.MTF_CONFLICT,
        "REGIME": ReasonCode.REGIME_CONFLICT,
    }
    out: list[str] = []
    for key, code in mapping.items():
        if key in r or key in gate_name.upper():
            out.append(code.value)
    if not out:
        out.append(f"{gate_name}:{reason}")
    return out


def explain_packet(
    *,
    signal: str,
    reason_codes: list[str],
    entry: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    size: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "signal": signal,
        "reason_codes": reason_codes,
        "why_buy": [c for c in reason_codes if c in {
            ReasonCode.TREND_CONFIRMED.value,
            ReasonCode.MTF_ALIGNMENT.value,
            ReasonCode.VOLUME_CONFIRMATION.value,
            ReasonCode.REGIME_SUPPORT.value,
            ReasonCode.EXPECTED_VALUE_POSITIVE.value,
        }],
        "why_blocked": [c for c in reason_codes if c.startswith(("DATA_", "RISK_", "SIGNAL_", "DUPLICATE", "KILL", "LIVE", "MARKET", "LOSS", "DRAWDOWN", "RATE", "MARTINGALE", "MISSING", "NEGATIVE", "RECONCILE", "MTF_", "REGIME_CONFLICT"))],
        "entry": entry,
        "stop": stop,
        "target": target,
        "size": size,
        "principle": "Opportunity score ≠ trading permission. Risk gate is final.",
        **(extra or {}),
    }
