"""Loss & drawdown governors — reduce aggression on losses; never increase risk (Master V2 §30–31).

States: NORMAL → CAUTION → REDUCED_RISK → TRADING_HALT
Limits are never auto-increased.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from config.settings import settings


class GovernorState(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    REDUCED_RISK = "REDUCED_RISK"
    TRADING_HALT = "TRADING_HALT"


@dataclass(frozen=True)
class GovernorDecision:
    state: GovernorState
    new_trades_allowed: bool
    size_mult: float
    reason: str
    daily_loss_pct: float
    drawdown_pct: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def evaluate_governors(
    *,
    daily_loss_pct: float,
    drawdown_pct: float,
    kill_switch: bool = False,
) -> GovernorDecision:
    """daily_loss_pct is typically negative when losing (ledger.daily_loss_pct)."""
    if kill_switch:
        return GovernorDecision(GovernorState.TRADING_HALT, False, 0.0, "KILL_SWITCH", daily_loss_pct, drawdown_pct)

    day_lim = float(settings.daily_max_loss_pct)
    dd_lim = float(settings.max_drawdown_pct)
    def_dd = float(getattr(settings, "defensive_dd_pct", 4.0))
    high_dd = float(getattr(settings, "high_risk_dd_pct", 7.0))
    cap_dd = float(getattr(settings, "capital_protection_dd_pct", 10.0))

    # Normalize: treat magnitude of loss
    day_loss_mag = abs(min(0.0, daily_loss_pct))

    if day_loss_mag >= day_lim or drawdown_pct >= dd_lim:
        return GovernorDecision(
            GovernorState.TRADING_HALT,
            False,
            0.0,
            "DAILY_LOSS_OR_MAX_DRAWDOWN",
            daily_loss_pct,
            drawdown_pct,
        )
    if drawdown_pct >= cap_dd or day_loss_mag >= day_lim * 0.85:
        return GovernorDecision(
            GovernorState.REDUCED_RISK,
            True,
            0.35,
            "APPROACHING_HARD_LIMIT",
            daily_loss_pct,
            drawdown_pct,
        )
    if drawdown_pct >= high_dd or day_loss_mag >= day_lim * 0.6:
        return GovernorDecision(
            GovernorState.CAUTION,
            True,
            0.55,
            "ELEVATED_DRAWDOWN_OR_DAILY_LOSS",
            daily_loss_pct,
            drawdown_pct,
        )
    if drawdown_pct >= def_dd or day_loss_mag >= day_lim * 0.35:
        return GovernorDecision(
            GovernorState.CAUTION,
            True,
            0.75,
            "DEFENSIVE_ZONE",
            daily_loss_pct,
            drawdown_pct,
        )
    return GovernorDecision(GovernorState.NORMAL, True, 1.0, "ok", daily_loss_pct, drawdown_pct)
