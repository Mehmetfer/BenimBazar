from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings, settings as default_settings


@dataclass
class SafetyGate:
    cfg: Settings = default_settings
    halted: bool = False
    reason: str = ""

    def evaluate(
        self,
        *,
        data_fresh: bool,
        api_ok: bool,
        order_status_ok: bool,
        spread_pct: float,
        daily_loss_pct: float,
        clock_ok: bool,
        max_spread_pct: float = 1.0,
    ) -> tuple[bool, str]:
        if self.cfg.kill_switch:
            return self._halt("KILL_SWITCH")
        if not api_ok:
            return self._halt("API_DOWN")
        if not data_fresh:
            return self._halt("STALE_DATA")
        if not order_status_ok:
            return self._halt("ORDER_STATUS_UNKNOWN")
        if spread_pct > max_spread_pct:
            return self._halt("ABNORMAL_SPREAD")
        if daily_loss_pct <= -self.cfg.daily_max_loss_pct:
            return self._halt("DAILY_LOSS_LIMIT")
        if not clock_ok:
            return self._halt("CLOCK_MISMATCH")
        if self.cfg.is_live:
            return self._halt("LIVE_BLOCKED_UNTIL_PREFLIGHT")
        self.halted = False
        self.reason = ""
        return True, "ok"

    def _halt(self, reason: str) -> tuple[bool, str]:
        self.halted = True
        self.reason = reason
        return False, reason
