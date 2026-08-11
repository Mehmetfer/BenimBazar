from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings, settings as default_settings
from engines.mode_selector import ModeDecision


@dataclass
class CapitalSleeves:
    total: float
    long_term: float
    swing: float
    day_trading: float
    cash_reserve: float
    effective_cash_target: float

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 2),
            "long_term": round(self.long_term, 2),
            "swing": round(self.swing, 2),
            "day_trading": round(self.day_trading, 2),
            "cash_reserve": round(self.cash_reserve, 2),
            "effective_cash_target": round(self.effective_cash_target, 2),
            "note": "Sleeves are hard budgets — one engine must not silently drain another.",
        }


def allocate_sleeves(equity: float, mode: ModeDecision | None = None, cfg: Settings | None = None) -> CapitalSleeves:
    cfg = cfg or default_settings
    lt = equity * cfg.long_term_capital_pct
    sw = equity * cfg.swing_capital_pct
    day = equity * cfg.day_trading_capital_pct
    cash = equity * cfg.cash_reserve_pct
    # Normalize small float drift
    s = lt + sw + day + cash
    if s > 0 and abs(s - equity) > 1:
        scale = equity / s
        lt, sw, day, cash = lt * scale, sw * scale, day * scale, cash * scale
    cash_target = cash
    if mode:
        # Increase cash when mode asks; shrink day/swing first
        extra = max(0.0, mode.cash_bias - cfg.cash_reserve_pct) * equity
        if extra > 0:
            take_day = min(day * 0.5, extra * 0.6)
            take_sw = min(sw * 0.3, extra - take_day)
            day -= take_day
            sw -= take_sw
            cash += take_day + take_sw
            cash_target = cash
        if mode.primary.value == "NO_TRADE":
            cash_target = max(cash_target, equity * 0.45)
    return CapitalSleeves(equity, lt, sw, day, cash, cash_target)
