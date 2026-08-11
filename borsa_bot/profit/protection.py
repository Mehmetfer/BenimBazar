from __future__ import annotations

from dataclasses import dataclass

from config.models import IndicatorSet
from config.settings import Settings, settings as default_settings


@dataclass
class ProfitProtectState:
    stop: float
    trailing_stop: float | None
    breakeven_armed: bool
    partial_exits_done: tuple[bool, bool, bool]  # t1,t2,t3
    reason: str


def initial_protect(entry: float, stop: float) -> ProfitProtectState:
    return ProfitProtectState(
        stop=stop,
        trailing_stop=None,
        breakeven_armed=False,
        partial_exits_done=(False, False, False),
        reason="initial",
    )


def update_profit_protection(
    *,
    entry: float,
    price: float,
    stop: float,
    ind: IndicatorSet,
    t1: float,
    t2: float,
    t3: float,
    state: ProfitProtectState,
    momentum_ok: bool,
    cfg: Settings | None = None,
) -> tuple[ProfitProtectState, float | None]:
    """
    Returns updated state and optional partial exit fraction (0-1) to sell now.
    Rules:
    - Never widen stop on a loser
    - No DCA here
    - Move to breakeven after +1R
    - Then ATR trailing if momentum continues
    """
    cfg = cfg or default_settings
    risk = entry - stop
    if risk <= 0:
        return state, None

    new_stop = state.stop
    # Never widen (lower stop for long)
    # Profit protection
    r_multiple = (price - entry) / risk
    breakeven_armed = state.breakeven_armed
    if r_multiple >= cfg.breakeven_r_multiple:
        breakeven = entry * (1 + cfg.commission_pct)  # cover costs roughly
        new_stop = max(new_stop, breakeven)
        breakeven_armed = True

    trail = state.trailing_stop
    if breakeven_armed and momentum_ok:
        atr_trail = price - ind.atr14 * cfg.atr_trail_mult
        ema_trail = ind.ema21
        candidate = max(atr_trail, ema_trail * 0.998)
        trail = max(trail or 0.0, candidate, new_stop)
        new_stop = max(new_stop, trail)
    elif breakeven_armed and not momentum_ok:
        # protect profits when momentum breaks
        new_stop = max(new_stop, entry)
        trail = new_stop

    # Partial take-profits
    t1_done, t2_done, t3_done = state.partial_exits_done
    exit_pct = None
    if price >= t1 and not t1_done:
        exit_pct = cfg.tp1_exit_pct
        t1_done = True
    elif price >= t2 and not t2_done:
        exit_pct = cfg.tp2_exit_pct
        t2_done = True
    elif price >= t3 and not t3_done:
        exit_pct = cfg.tp3_exit_pct
        t3_done = True

    # Loss control: if price hit stop, full exit signaled by caller via stop check
    if new_stop < state.stop:
        new_stop = state.stop  # hard rule: never widen

    updated = ProfitProtectState(
        stop=round(new_stop, 4),
        trailing_stop=round(trail, 4) if trail else None,
        breakeven_armed=breakeven_armed,
        partial_exits_done=(t1_done, t2_done, t3_done),
        reason="protect_update",
    )
    return updated, exit_pct


def refuse_add_to_loser(*, avg_cost: float, price: float, allow_dca: bool | None = None) -> bool:
    """Return True if add-on must be refused."""
    cfg_allow = default_settings.allow_dca if allow_dca is None else allow_dca
    if cfg_allow:
        return False
    return price < avg_cost
