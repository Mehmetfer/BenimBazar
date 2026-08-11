from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import Settings, settings as default_settings


@dataclass
class DayTradingRiskState:
    trades_today: int = 0
    consecutive_losses: int = 0
    realized_pnl_today: float = 0.0
    paused: bool = False
    pause_reason: str = ""
    reasons: list[str] = field(default_factory=list)

    def register_trade(self, pnl: float | None = None) -> None:
        self.trades_today += 1
        if pnl is not None:
            self.realized_pnl_today += pnl
            if pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

    def evaluate(self, *, equity: float, open_day_exposure: float, cfg: Settings | None = None) -> "DayTradingRiskState":
        cfg = cfg or default_settings
        self.reasons = []
        self.paused = False
        self.pause_reason = ""
        loss_lim = equity * (cfg.day_max_daily_loss_pct / 100)
        if self.realized_pnl_today <= -loss_lim:
            self.paused = True
            self.pause_reason = "DAY_MAX_DAILY_LOSS"
        elif self.trades_today >= cfg.day_max_trades:
            self.paused = True
            self.pause_reason = "DAY_MAX_TRADES"
        elif self.consecutive_losses >= cfg.day_max_consecutive_losses:
            self.paused = True
            self.pause_reason = "DAY_MAX_CONSECUTIVE_LOSSES"
        elif open_day_exposure > equity * (cfg.day_max_exposure_pct / 100):
            self.paused = True
            self.pause_reason = "DAY_MAX_EXPOSURE"
        if self.paused:
            self.reasons.append(self.pause_reason)
        return self
