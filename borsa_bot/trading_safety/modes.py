"""Execution modes for trading safety — distinct from research Level-8 claims."""

from __future__ import annotations

from enum import Enum


class TradingExecutionMode(str, Enum):
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    MICRO_LIVE = "MICRO_LIVE"  # hard-capped; still requires LIVE unlock + human confirmation
    LIVE = "LIVE"  # full live — blocked unless explicitly unlocked (never auto)


def parse_trading_mode(raw: str | None) -> TradingExecutionMode:
    key = (raw or "PAPER").strip().upper()
    aliases = {
        "SIM": "PAPER",
        "SIMULATED": "PAPER",
        "WOULD": "SHADOW",
        "DRY": "SHADOW",
        "DRY_RUN": "SHADOW",
        "MICRO": "MICRO_LIVE",
        "MICROLIVE": "MICRO_LIVE",
        "TINY": "MICRO_LIVE",
    }
    key = aliases.get(key, key)
    try:
        return TradingExecutionMode(key)
    except ValueError:
        return TradingExecutionMode.PAPER


def may_touch_real_broker(mode: TradingExecutionMode) -> bool:
    """Only MICRO_LIVE/LIVE *may* touch a broker adapter — still gated elsewhere."""
    return mode in {TradingExecutionMode.MICRO_LIVE, TradingExecutionMode.LIVE}


def real_orders_forbidden_without_unlock(mode: TradingExecutionMode) -> bool:
    return mode in {TradingExecutionMode.PAPER, TradingExecutionMode.SHADOW}
