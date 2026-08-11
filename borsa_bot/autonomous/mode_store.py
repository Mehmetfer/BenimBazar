"""Runtime user trading mode override — does not unlock LIVE broker."""

from __future__ import annotations

import json
from pathlib import Path

from autonomous.modes import UserTradingMode, parse_user_mode
from config.settings import ROOT, settings


class AutonomyModeStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "autonomy_mode.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> UserTradingMode:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return parse_user_mode(data.get("user_trading_mode"))
            except Exception:  # noqa: BLE001
                pass
        return parse_user_mode(getattr(settings, "user_trading_mode", "PAPER"))

    def set(self, mode: str | UserTradingMode) -> UserTradingMode:
        m = mode if isinstance(mode, UserTradingMode) else parse_user_mode(str(mode))
        # Never allow a "LIVE" alias through this store
        if str(mode).upper() in {"LIVE", "LIVE_BROKER", "REAL"}:
            m = UserTradingMode.PAPER
        self.path.write_text(
            json.dumps(
                {
                    "user_trading_mode": m.value,
                    "live_broker": "DISABLED",
                    "note": "AUTO means automated paper trading only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return m


mode_store = AutonomyModeStore()
