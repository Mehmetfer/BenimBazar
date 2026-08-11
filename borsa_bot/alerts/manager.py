from __future__ import annotations

from alerts.bus import EventBus
from alerts.channels.in_app import InAppChannel
from alerts.channels.push import PushChannel
from alerts.channels.sms import SmsChannel
from alerts.channels.sound import SoundChannel
from alerts.channels.tts import TtsChannel
from alerts.cooldown import CooldownGate, Deduper
from alerts.events import (
    QUIET_HOURS_BYPASS,
    AlertChannel,
    AlertEventType,
    AlertPriority,
    TradingAlertEvent,
)
from alerts.log import NotificationLog
from alerts.messages import format_alert
from alerts.settings_store import (
    ChannelToggles,
    NotificationSettingsStore,
    UserNotificationSettings,
    current_hhmm,
    in_quiet_hours,
)


# Map event types → preference category
_PREF_MAP: dict[AlertEventType, str] = {
    AlertEventType.BUY_SIGNAL: "buy",
    AlertEventType.SELL_SIGNAL: "sell",
    AlertEventType.STOP_LOSS: "stop",
    AlertEventType.TAKE_PROFIT: "take_profit",
    AlertEventType.TRAILING_STOP: "take_profit",
    AlertEventType.RISK_ALERT: "risk",
    AlertEventType.KILL_SWITCH: "kill_switch",
    AlertEventType.DATA_FEED_FAILURE: "risk",
    AlertEventType.BROKER_API_FAILURE: "risk",
    AlertEventType.NEWS_ALERT: "news",
    AlertEventType.DAILY_SUMMARY: "daily_report",
    AlertEventType.ORDER_SUBMITTED: "order_status",
    AlertEventType.ORDER_ACCEPTED: "order_status",
    AlertEventType.ORDER_PARTIAL: "order_status",
    AlertEventType.ORDER_FILLED: "order_status",
    AlertEventType.ORDER_CANCELLED: "order_status",
    AlertEventType.ORDER_REJECTED: "order_status",
    AlertEventType.WATCH_SIGNAL: "news",
    AlertEventType.MARKET_UPDATE: "news",
    AlertEventType.ALERT_DELIVERY_FAILURE: "risk",
}


class AlertManager:
    """
    TRADING EVENT → EVENT BUS → ALERT MANAGER → PRIORITY → CHANNEL ROUTER
    → PUSH / SOUND / TTS / SMS / IN_APP → DELIVERY LOG

    Notifications never change trading decisions.
    Channel failures never halt the trading pipeline.
    """

    def __init__(
        self,
        bus: EventBus | None = None,
        log: NotificationLog | None = None,
        settings_store: NotificationSettingsStore | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.log = log or NotificationLog()
        self.settings_store = settings_store or NotificationSettingsStore()
        self.cooldown = CooldownGate(
            default_seconds=self.settings_store.get().cooldown_seconds
        )
        self.deduper = Deduper()
        self.in_app = InAppChannel(self.log)
        self.push = PushChannel()
        self.sound = SoundChannel()
        self.tts = TtsChannel()
        self.sms = SmsChannel()
        self.bus.subscribe(self.handle)

    def publish(self, event: TradingAlertEvent) -> None:
        """Safe entry: never raises to trading callers."""
        try:
            self.bus.publish(event)
        except Exception:  # noqa: BLE001
            try:
                self.log.write_delivery(
                    event_id=getattr(event, "event_id", "unknown"),
                    symbol=getattr(event, "symbol", None),
                    event_type=getattr(event, "event_type", AlertEventType.ALERT_DELIVERY_FAILURE).value
                    if hasattr(getattr(event, "event_type", None), "value")
                    else "ALERT_DELIVERY_FAILURE",
                    priority=AlertPriority.HIGH.value,
                    channel=AlertChannel.IN_APP.value,
                    message="alert_bus_publish_failure",
                    delivery_status="FAILED",
                    provider="alert_manager",
                    error="publish_exception",
                )
            except Exception:  # noqa: BLE001
                pass

    def handle(self, event: TradingAlertEvent) -> None:
        try:
            self._handle_inner(event)
        except Exception as exc:  # noqa: BLE001 — isolation
            try:
                self.log.write_delivery(
                    event_id=event.event_id,
                    symbol=event.symbol,
                    event_type=event.event_type.value,
                    priority=event.resolved_priority().value,
                    channel=AlertChannel.IN_APP.value,
                    message="ALERT DELIVERY FAILURE",
                    delivery_status="FAILED",
                    provider="alert_manager",
                    error=type(exc).__name__,
                )
            except Exception:  # noqa: BLE001
                pass

    def _handle_inner(self, event: TradingAlertEvent) -> None:
        if self.deduper.seen_or_mark(event.event_id):
            return

        user = self.settings_store.get()
        self.cooldown.default_seconds = user.cooldown_seconds

        # Cooldown: critical always allowed
        prio = event.resolved_priority()
        if prio != AlertPriority.CRITICAL:
            if not self.cooldown.allow(event.cooldown_key(), user.cooldown_seconds):
                self.log.write_delivery(
                    event_id=event.event_id,
                    symbol=event.symbol,
                    event_type=event.event_type.value,
                    priority=prio.value,
                    channel=AlertChannel.IN_APP.value,
                    message="suppressed_cooldown",
                    delivery_status="SUPPRESSED",
                    provider="cooldown",
                    timestamp=event.timestamp,
                )
                return

        # Quiet hours
        if user.quiet_hours_enabled and event.event_type not in QUIET_HOURS_BYPASS:
            if in_quiet_hours(current_hhmm(), user.quiet_hours_start, user.quiet_hours_end):
                self.log.write_delivery(
                    event_id=event.event_id,
                    symbol=event.symbol,
                    event_type=event.event_type.value,
                    priority=prio.value,
                    channel=AlertChannel.IN_APP.value,
                    message="suppressed_quiet_hours",
                    delivery_status="SUPPRESSED",
                    provider="quiet_hours",
                    timestamp=event.timestamp,
                )
                return

        event = format_alert(event)
        toggles = self._toggles_for(event.event_type, user)
        critical_failed = False

        plan: list[tuple[AlertChannel, object, bool]] = [
            (AlertChannel.IN_APP, self.in_app, toggles.in_app),
            (AlertChannel.PUSH, self.push, toggles.push and user.push_on),
            (AlertChannel.SOUND, self.sound, toggles.sound and user.sound_on),
            (AlertChannel.TTS, self.tts, toggles.voice and user.tts_on),
            (AlertChannel.SMS, self.sms, toggles.sms and user.sms_on),
        ]

        for channel, impl, enabled in plan:
            if not enabled:
                self.log.write_delivery(
                    event_id=event.event_id,
                    symbol=event.symbol,
                    event_type=event.event_type.value,
                    priority=prio.value,
                    channel=channel.value,
                    message=event.message,
                    delivery_status="SKIPPED",
                    provider=getattr(impl, "name", "n/a"),
                    timestamp=event.timestamp,
                )
                continue
            result = impl.send(event)
            status = "SENT" if result.ok else "FAILED"
            self.log.write_delivery(
                event_id=event.event_id,
                symbol=event.symbol,
                event_type=event.event_type.value,
                priority=prio.value,
                channel=channel.value,
                message=event.message if channel != AlertChannel.SOUND else (result.detail or event.message),
                delivery_status=status,
                provider=result.provider,
                error=result.error,
                timestamp=event.timestamp,
            )
            if not result.ok and prio == AlertPriority.CRITICAL:
                critical_failed = True

        if critical_failed:
            # Meta-log only — do not recurse infinitely
            self.log.write_delivery(
                event_id=event.event_id,
                symbol=event.symbol,
                event_type=AlertEventType.ALERT_DELIVERY_FAILURE.value,
                priority=AlertPriority.HIGH.value,
                channel=AlertChannel.IN_APP.value,
                message="ALERT DELIVERY FAILURE: critical channel failed",
                delivery_status="FAILED",
                provider="alert_manager",
                error="critical_channel_failure",
                timestamp=event.timestamp,
            )

    def _toggles_for(self, et: AlertEventType, user: UserNotificationSettings) -> ChannelToggles:
        key = _PREF_MAP.get(et, "news")
        return getattr(user.prefs, key, ChannelToggles())
