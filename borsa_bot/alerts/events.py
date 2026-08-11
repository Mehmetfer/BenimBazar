from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from config.models import utc_now


class AlertEventType(str, Enum):
    # SIGNAL ≠ EXECUTION — keep separate
    BUY_SIGNAL = "BUY_SIGNAL"
    SELL_SIGNAL = "SELL_SIGNAL"
    WATCH_SIGNAL = "WATCH_SIGNAL"
    MARKET_UPDATE = "MARKET_UPDATE"

    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"

    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_PARTIAL = "ORDER_PARTIAL"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"

    RISK_ALERT = "RISK_ALERT"
    KILL_SWITCH = "KILL_SWITCH"
    DATA_FEED_FAILURE = "DATA_FEED_FAILURE"
    BROKER_API_FAILURE = "BROKER_API_FAILURE"
    ALERT_DELIVERY_FAILURE = "ALERT_DELIVERY_FAILURE"

    NEWS_ALERT = "NEWS_ALERT"
    DAILY_SUMMARY = "DAILY_SUMMARY"


class AlertPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertChannel(str, Enum):
    IN_APP = "IN_APP"
    PUSH = "PUSH"
    SOUND = "SOUND"
    TTS = "TTS"
    SMS = "SMS"


class SoundProfile(str, Enum):
    INFO = "INFO"
    BUY = "BUY"
    SELL = "SELL"
    PROFIT = "PROFIT"
    STOP = "STOP"
    CRITICAL = "CRITICAL"


DEFAULT_PRIORITY: dict[AlertEventType, AlertPriority] = {
    AlertEventType.MARKET_UPDATE: AlertPriority.LOW,
    AlertEventType.WATCH_SIGNAL: AlertPriority.NORMAL,
    AlertEventType.DAILY_SUMMARY: AlertPriority.NORMAL,
    AlertEventType.NEWS_ALERT: AlertPriority.NORMAL,
    AlertEventType.BUY_SIGNAL: AlertPriority.HIGH,
    AlertEventType.SELL_SIGNAL: AlertPriority.HIGH,
    AlertEventType.TAKE_PROFIT: AlertPriority.HIGH,
    AlertEventType.TRAILING_STOP: AlertPriority.HIGH,
    AlertEventType.ORDER_SUBMITTED: AlertPriority.NORMAL,
    AlertEventType.ORDER_ACCEPTED: AlertPriority.NORMAL,
    AlertEventType.ORDER_PARTIAL: AlertPriority.NORMAL,
    AlertEventType.ORDER_FILLED: AlertPriority.HIGH,
    AlertEventType.ORDER_CANCELLED: AlertPriority.HIGH,
    AlertEventType.ORDER_REJECTED: AlertPriority.CRITICAL,
    AlertEventType.STOP_LOSS: AlertPriority.CRITICAL,
    AlertEventType.RISK_ALERT: AlertPriority.CRITICAL,
    AlertEventType.KILL_SWITCH: AlertPriority.CRITICAL,
    AlertEventType.DATA_FEED_FAILURE: AlertPriority.CRITICAL,
    AlertEventType.BROKER_API_FAILURE: AlertPriority.CRITICAL,
    AlertEventType.ALERT_DELIVERY_FAILURE: AlertPriority.HIGH,
}

SOUND_FOR_EVENT: dict[AlertEventType, SoundProfile] = {
    AlertEventType.BUY_SIGNAL: SoundProfile.BUY,
    AlertEventType.SELL_SIGNAL: SoundProfile.SELL,
    AlertEventType.TAKE_PROFIT: SoundProfile.PROFIT,
    AlertEventType.TRAILING_STOP: SoundProfile.PROFIT,
    AlertEventType.STOP_LOSS: SoundProfile.STOP,
    AlertEventType.ORDER_REJECTED: SoundProfile.CRITICAL,
    AlertEventType.KILL_SWITCH: SoundProfile.CRITICAL,
    AlertEventType.RISK_ALERT: SoundProfile.CRITICAL,
    AlertEventType.DATA_FEED_FAILURE: SoundProfile.CRITICAL,
    AlertEventType.BROKER_API_FAILURE: SoundProfile.CRITICAL,
}

# Quiet hours may suppress non-critical; these always pass.
QUIET_HOURS_BYPASS = {
    AlertEventType.STOP_LOSS,
    AlertEventType.KILL_SWITCH,
    AlertEventType.RISK_ALERT,
    AlertEventType.ORDER_REJECTED,
    AlertEventType.DATA_FEED_FAILURE,
    AlertEventType.BROKER_API_FAILURE,
}


@dataclass
class TradingAlertEvent:
    """Immutable trading-domain event fed into the alert bus. Never mutates trading."""

    event_type: AlertEventType
    symbol: str | None = None
    title: str = ""
    message: str = ""
    priority: AlertPriority | None = None
    strategy: str | None = None
    price: float | None = None
    confidence: float | None = None
    risk_reward: float | None = None
    stop: float | None = None
    target: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())
    dedupe_key: str | None = None
    sound_profile: SoundProfile | None = None
    tts_text: str | None = None

    def resolved_priority(self) -> AlertPriority:
        if self.priority is not None:
            return self.priority
        return DEFAULT_PRIORITY.get(self.event_type, AlertPriority.NORMAL)

    def resolved_sound(self) -> SoundProfile:
        if self.sound_profile is not None:
            return self.sound_profile
        return SOUND_FOR_EVENT.get(self.event_type, SoundProfile.INFO)

    def cooldown_key(self) -> str:
        if self.dedupe_key:
            return self.dedupe_key
        return f"{self.event_type.value}:{self.symbol or '*'}"
