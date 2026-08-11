"""Autonomy maturity levels (Master V2) — display + capability gates.

LEVEL 0 MANUAL … LEVEL 5 FULL AUTONOMOUS
LIVE levels never unlock broker without LIVE_BROKER_ENABLED + confirmation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any

from autonomous.execution_modes import ExecutionMode
from autonomous.modes import UserTradingMode
from config.settings import settings


class AutonomyLevel(IntEnum):
    LEVEL_0_MANUAL = 0
    LEVEL_1_ASSISTED = 1
    LEVEL_2_PAPER_AUTONOMOUS = 2
    LEVEL_3_SHADOW_LIVE = 3
    LEVEL_4_CONTROLLED_LIVE = 4
    LEVEL_5_FULL_AUTONOMOUS = 5


_LABELS = {
    AutonomyLevel.LEVEL_0_MANUAL: "MANUAL",
    AutonomyLevel.LEVEL_1_ASSISTED: "ASSISTED",
    AutonomyLevel.LEVEL_2_PAPER_AUTONOMOUS: "PAPER_AUTONOMOUS",
    AutonomyLevel.LEVEL_3_SHADOW_LIVE: "SHADOW_LIVE",
    AutonomyLevel.LEVEL_4_CONTROLLED_LIVE: "CONTROLLED_LIVE",
    AutonomyLevel.LEVEL_5_FULL_AUTONOMOUS: "FULL_AUTONOMOUS",
}


@dataclass(frozen=True)
class AutonomyLevelStatus:
    level: int
    label: str
    user_trading_mode: str
    execution_mode: str
    can_scan: bool
    can_auto_paper: bool
    can_shadow: bool
    can_live: bool
    live_unlocked: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_autonomy_level(
    user_mode: UserTradingMode,
    execution_mode: ExecutionMode,
    *,
    blocked: bool = False,
) -> AutonomyLevelStatus:
    live_flag = bool(getattr(settings, "live_broker_enabled", False))
    live_confirmed = bool(getattr(settings, "live_confirmed", False))
    live_unlocked = live_flag and live_confirmed

    if blocked or user_mode is UserTradingMode.PAUSED:
        level = AutonomyLevel.LEVEL_0_MANUAL
        note = "PAUSED/BLOCKED — analysis may continue; no new autonomous orders"
        if user_mode is UserTradingMode.PAUSED:
            note = "PAUSED"
    elif execution_mode is ExecutionMode.LIVE and live_unlocked and user_mode is UserTradingMode.AUTO:
        # Still not FULL until real broker adapter exists — cap at 4 when flag-only
        level = AutonomyLevel.LEVEL_4_CONTROLLED_LIVE
        note = "CONTROLLED_LIVE flags set — real broker adapter still required for fills"
    elif execution_mode is ExecutionMode.SHADOW:
        level = AutonomyLevel.LEVEL_3_SHADOW_LIVE
        note = "SHADOW — real analysis path; WOULD_* intents only; no broker orders"
    elif user_mode is UserTradingMode.AUTO and execution_mode is ExecutionMode.PAPER:
        level = AutonomyLevel.LEVEL_2_PAPER_AUTONOMOUS
        note = "Paper autonomous — gated paper fills only"
    elif user_mode is UserTradingMode.SEMI_AUTO:
        level = AutonomyLevel.LEVEL_1_ASSISTED
        note = "Assisted — scan/plans; human approval for fills"
    else:
        level = AutonomyLevel.LEVEL_0_MANUAL
        note = "Manual / dashboard-driven paper"

    # LEVEL 5 never auto-granted
    if level >= AutonomyLevel.LEVEL_5_FULL_AUTONOMOUS:
        level = AutonomyLevel.LEVEL_4_CONTROLLED_LIVE
        note = "FULL AUTONOMOUS not available — institutional gates incomplete"

    return AutonomyLevelStatus(
        level=int(level),
        label=_LABELS[AutonomyLevel(level)],
        user_trading_mode=user_mode.value,
        execution_mode=execution_mode.value,
        can_scan=user_mode is not UserTradingMode.PAUSED or True,
        can_auto_paper=user_mode is UserTradingMode.AUTO and execution_mode is ExecutionMode.PAPER,
        can_shadow=execution_mode is ExecutionMode.SHADOW,
        can_live=False,  # hard: never claim live capability until adapter + unlock
        live_unlocked=live_unlocked,
        note=note,
    )
