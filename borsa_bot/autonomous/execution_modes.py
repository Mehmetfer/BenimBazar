"""Execution venue modes — distinct from UserTradingMode (PAPER/SEMI_AUTO/AUTO/PAUSED).

PAPER  — real or simulated data allowed per APP_ENV; fills go to PaperBroker only.
SHADOW — observe + plan + WOULD_* intents; no orders submitted.
LIVE   — real broker path; hard-blocked unless LIVE_BROKER_ENABLED + adapter ready.
"""

from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


def parse_execution_mode(raw: str | None) -> ExecutionMode:
    key = (raw or "PAPER").strip().upper()
    aliases = {
        "SIM": "PAPER",
        "SIMULATED": "PAPER",
        "WOULD": "SHADOW",
        "DRY": "SHADOW",
        "DRY_RUN": "SHADOW",
        "DRYRUN": "SHADOW",
    }
    key = aliases.get(key, key)
    try:
        return ExecutionMode(key)
    except ValueError:
        return ExecutionMode.PAPER


def orders_may_submit(mode: ExecutionMode) -> bool:
    """SHADOW never submits. LIVE only via separate live broker unlock."""
    return mode is ExecutionMode.PAPER
