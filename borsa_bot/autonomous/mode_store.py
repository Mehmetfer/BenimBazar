"""Runtime mode overrides — does not unlock live broker by itself."""

from __future__ import annotations

import json
from pathlib import Path

from autonomous.execution_modes import ExecutionMode, parse_execution_mode
from autonomous.modes import UserTradingMode, parse_user_mode
from config.settings import ROOT, settings


class AutonomyModeStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "autonomy_mode.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                pass
        return {}

    def _write(self, data: dict) -> None:
        data.setdefault("live_broker", "DISABLED")
        data.setdefault(
            "note",
            "UserTradingMode AUTO = automated paper. ExecutionMode LIVE requires LIVE_BROKER_ENABLED + adapter.",
        )
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self) -> UserTradingMode:
        data = self._read()
        if data.get("user_trading_mode"):
            return parse_user_mode(data.get("user_trading_mode"))
        return parse_user_mode(getattr(settings, "user_trading_mode", "PAPER"))

    def get_execution_mode(self) -> ExecutionMode:
        data = self._read()
        if data.get("execution_mode"):
            return parse_execution_mode(data.get("execution_mode"))
        return parse_execution_mode(getattr(settings, "execution_mode", "PAPER"))

    def set(self, mode: str | UserTradingMode) -> UserTradingMode:
        raw = str(mode).upper()
        # LIVE as user mode is rejected — use execution_mode instead
        if raw in {"LIVE", "LIVE_BROKER", "REAL", "REAL_MONEY"}:
            m = UserTradingMode.PAPER
        else:
            m = mode if isinstance(mode, UserTradingMode) else parse_user_mode(str(mode))
        data = self._read()
        data["user_trading_mode"] = m.value
        if "execution_mode" not in data:
            data["execution_mode"] = self.get_execution_mode().value
        self._write(data)
        return m

    def set_execution_mode(self, mode: str | ExecutionMode) -> ExecutionMode:
        m = mode if isinstance(mode, ExecutionMode) else parse_execution_mode(str(mode))
        # Selecting LIVE does not enable broker — flag must be set separately
        data = self._read()
        data["execution_mode"] = m.value
        if "user_trading_mode" not in data:
            data["user_trading_mode"] = self.get().value
        data["live_broker_enabled_flag"] = bool(getattr(settings, "live_broker_enabled", False))
        self._write(data)
        return m


mode_store = AutonomyModeStore()
