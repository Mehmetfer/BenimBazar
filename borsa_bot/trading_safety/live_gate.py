"""Runtime live-money gate — user can open/close without env restart.

Env flags (LIVE_BROKER_ENABLED / LIVE_CONFIRMED) remain authoritative when set.
This store is an additional human UI latch. It does NOT load a real broker
adapter; LiveBrokerDisabled still blocks fills until a real adapter exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import ROOT, settings

CONFIRM_PHRASE = "I_UNDERSTAND_LIVE_RISK"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveGateSnapshot:
    user_enabled: bool
    confirmed_at: str | None
    confirmed_by: str
    source: str  # env | ui | off
    broker_enabled: bool
    confirmed: bool
    real_adapter: bool
    can_send_live_orders: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "user_enabled": self.user_enabled,
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "source": self.source,
            "broker_enabled": self.broker_enabled,
            "confirmed": self.confirmed,
            "real_adapter": self.real_adapter,
            "can_send_live_orders": self.can_send_live_orders,
            "message": self.message,
            "open": self.broker_enabled and self.confirmed,
        }


class LiveGateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "live_gate.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                pass
        return {"user_enabled": False}

    def _write(self, data: dict) -> None:
        data["updated_at"] = _utcnow()
        data.setdefault(
            "note",
            "UI latch only — real fills need a real BrokerAdapter + this gate open",
        )
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_user_enabled(self) -> bool:
        return bool(self._read().get("user_enabled"))

    def enable(self, *, phrase: str, confirmed_by: str = "dashboard") -> LiveGateSnapshot:
        if (phrase or "").strip().upper() != CONFIRM_PHRASE:
            raise ValueError(f"Confirmation phrase required: {CONFIRM_PHRASE}")
        self._write(
            {
                "user_enabled": True,
                "confirmed_at": _utcnow(),
                "confirmed_by": (confirmed_by or "dashboard")[:80],
                "phrase_ok": True,
            }
        )
        return self.snapshot()

    def disable(self, *, by: str = "dashboard") -> LiveGateSnapshot:
        data = self._read()
        data["user_enabled"] = False
        data["disabled_at"] = _utcnow()
        data["disabled_by"] = (by or "dashboard")[:80]
        data["confirmed_at"] = None
        self._write(data)
        return self.snapshot()

    def snapshot(self) -> LiveGateSnapshot:
        data = self._read()
        user_on = bool(data.get("user_enabled"))
        env_on = bool(getattr(settings, "live_broker_enabled", False))
        env_conf = bool(getattr(settings, "live_confirmed", False))
        confirm_req = bool(getattr(settings, "live_confirmation_required", True))

        broker_enabled = env_on or user_on
        if confirm_req:
            confirmed = env_conf or user_on
        else:
            confirmed = True

        if env_on and env_conf:
            source = "env"
        elif user_on:
            source = "ui"
        else:
            source = "off"

        real_adapter = False
        try:
            from execution.live_factory import live_adapter_status

            real_adapter = bool(live_adapter_status().get("real_adapter_loaded"))
        except Exception:  # noqa: BLE001
            real_adapter = False

        can_send = broker_enabled and confirmed and real_adapter and not bool(
            getattr(settings, "kill_switch", False)
        )

        if not broker_enabled:
            msg = "Canlı para kapalı · sadece paper"
        elif not real_adapter:
            msg = "Canlı kapı açık · gerçek broker bağlı değil · emir gönderilmez"
        elif can_send:
            msg = "Canlı kapı açık · broker bağlı · dikkat: gerçek para"
        else:
            msg = "Canlı kapı kısmen açık · ek kilitler var"

        return LiveGateSnapshot(
            user_enabled=user_on,
            confirmed_at=data.get("confirmed_at"),
            confirmed_by=str(data.get("confirmed_by") or ""),
            source=source,
            broker_enabled=broker_enabled,
            confirmed=confirmed,
            real_adapter=real_adapter,
            can_send_live_orders=can_send,
            message=msg,
        )


live_gate_store = LiveGateStore()


def is_live_broker_enabled() -> bool:
    """Effective LIVE_BROKER_ENABLED (env OR UI gate)."""
    return bool(getattr(settings, "live_broker_enabled", False)) or live_gate_store.is_user_enabled()


def is_live_confirmed() -> bool:
    """Effective LIVE_CONFIRMED (env OR UI gate)."""
    if not bool(getattr(settings, "live_confirmation_required", True)):
        return True
    return bool(getattr(settings, "live_confirmed", False)) or live_gate_store.is_user_enabled()


def live_gate_status() -> dict:
    return live_gate_store.snapshot().to_dict()
