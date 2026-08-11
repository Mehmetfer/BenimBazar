"""Autonomous trading user modes — PAPER only for automatic execution.

AUTO = automated PAPER trading (never live broker).
LIVE broker remains a locked future phase.
"""

from __future__ import annotations

from enum import Enum


class UserTradingMode(str, Enum):
    PAPER = "PAPER"  # manual / dashboard-driven paper
    SEMI_AUTO = "SEMI_AUTO"  # autonomous scan + plans; no auto fill
    AUTO = "AUTO"  # autonomous paper execution through gates
    PAUSED = "PAUSED"  # no new analysis orders; monitor may continue


def parse_user_mode(raw: str | None) -> UserTradingMode:
    key = (raw or "PAPER").strip().upper().replace("-", "_")
    aliases = {"SEMI": "SEMI_AUTO", "SEMI_AUTOMATIC": "SEMI_AUTO", "AUTOMATIC": "AUTO"}
    key = aliases.get(key, key)
    try:
        return UserTradingMode(key)
    except ValueError:
        return UserTradingMode.PAPER


def auto_paper_allowed(mode: UserTradingMode) -> bool:
    """True only when autonomous paper fills are permitted."""
    return mode == UserTradingMode.AUTO


def analysis_allowed(mode: UserTradingMode) -> bool:
    return mode in {UserTradingMode.PAPER, UserTradingMode.SEMI_AUTO, UserTradingMode.AUTO}
