from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config.settings import ROOT, settings


@dataclass
class ChannelToggles:
    push: bool = True
    sms: bool = False
    sound: bool = True
    voice: bool = True  # TTS
    in_app: bool = True


@dataclass
class EventAlertPrefs:
    """Per-event-category channel preferences."""

    buy: ChannelToggles = field(default_factory=ChannelToggles)
    sell: ChannelToggles = field(default_factory=lambda: ChannelToggles(sms=False))
    stop: ChannelToggles = field(
        default_factory=lambda: ChannelToggles(push=True, sms=True, sound=True, voice=True)
    )
    take_profit: ChannelToggles = field(
        default_factory=lambda: ChannelToggles(sms=False, sound=True, voice=True)
    )
    risk: ChannelToggles = field(
        default_factory=lambda: ChannelToggles(push=True, sms=True, sound=True, voice=True)
    )
    kill_switch: ChannelToggles = field(
        default_factory=lambda: ChannelToggles(push=True, sms=True, sound=True, voice=True)
    )
    news: ChannelToggles = field(default_factory=lambda: ChannelToggles(sms=False, sound=False))
    daily_report: ChannelToggles = field(
        default_factory=lambda: ChannelToggles(sms=False, sound=False, voice=False)
    )
    order_status: ChannelToggles = field(default_factory=lambda: ChannelToggles(sms=False))


@dataclass
class UserNotificationSettings:
    """User-facing notification preferences. Does not affect trading decisions."""

    sms_on: bool = False
    push_on: bool = True
    sound_on: bool = True
    tts_on: bool = True
    sound_volume: float = 0.7  # 0..1
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"  # HH:MM local-ish (UTC used if no TZ)
    quiet_hours_end: str = "07:00"
    cooldown_seconds: int = 300
    prefs: EventAlertPrefs = field(default_factory=EventAlertPrefs)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> UserNotificationSettings:
        prefs_raw = data.get("prefs") or {}
        prefs = EventAlertPrefs()
        for name in (
            "buy",
            "sell",
            "stop",
            "take_profit",
            "risk",
            "kill_switch",
            "news",
            "daily_report",
            "order_status",
        ):
            raw = prefs_raw.get(name)
            if isinstance(raw, dict):
                setattr(
                    prefs,
                    name,
                    ChannelToggles(
                        push=bool(raw.get("push", True)),
                        sms=bool(raw.get("sms", False)),
                        sound=bool(raw.get("sound", True)),
                        voice=bool(raw.get("voice", True)),
                        in_app=bool(raw.get("in_app", True)),
                    ),
                )
        return cls(
            sms_on=bool(data.get("sms_on", False)),
            push_on=bool(data.get("push_on", True)),
            sound_on=bool(data.get("sound_on", True)),
            tts_on=bool(data.get("tts_on", True)),
            sound_volume=float(data.get("sound_volume", 0.7)),
            quiet_hours_enabled=bool(data.get("quiet_hours_enabled", False)),
            quiet_hours_start=str(data.get("quiet_hours_start", "22:00")),
            quiet_hours_end=str(data.get("quiet_hours_end", "07:00")),
            cooldown_seconds=int(data.get("cooldown_seconds", 300)),
            prefs=prefs,
        )


class NotificationSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "notification_settings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = self._load()

    def _load(self) -> UserNotificationSettings:
        if not self.path.exists():
            s = UserNotificationSettings(
                sms_on=bool(getattr(settings, "sms_on", False)),
                push_on=bool(getattr(settings, "push_on", True)),
                sound_on=bool(getattr(settings, "sound_on", True)),
                tts_on=bool(getattr(settings, "tts_on", True)),
                cooldown_seconds=int(getattr(settings, "alert_cooldown_seconds", 300)),
            )
            self._save(s)
            return s
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return UserNotificationSettings.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return UserNotificationSettings()

    def _save(self, s: UserNotificationSettings) -> None:
        self.path.write_text(json.dumps(s.to_dict(), indent=2), encoding="utf-8")

    def get(self) -> UserNotificationSettings:
        return self._settings

    def update(self, patch: dict) -> UserNotificationSettings:
        merged = self._settings.to_dict()
        for k, v in patch.items():
            if k == "prefs" and isinstance(v, dict):
                prefs = merged.get("prefs") or {}
                for pk, pv in v.items():
                    if isinstance(pv, dict):
                        prefs[pk] = {**(prefs.get(pk) or {}), **pv}
                    else:
                        prefs[pk] = pv
                merged["prefs"] = prefs
            else:
                merged[k] = v
        self._settings = UserNotificationSettings.from_dict(merged)
        self._save(self._settings)
        return self._settings


def in_quiet_hours(now_hhmm: str, start: str, end: str) -> bool:
    """Return True if now is inside quiet window. Supports overnight windows."""
    if start == end:
        return False
    if start < end:
        return start <= now_hhmm < end
    # overnight e.g. 22:00 -> 07:00
    return now_hhmm >= start or now_hhmm < end


def current_hhmm() -> str:
    # Use local clock for UX; alert layer does not drive trading.
    return time.strftime("%H:%M")
