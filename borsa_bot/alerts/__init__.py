from __future__ import annotations

from alerts.bridge import (
    emit_daily_summary,
    emit_execution_exit,
    emit_kill_switch,
    emit_order_lifecycle,
    emit_risk_alert,
    emit_signal_alerts,
)
from alerts.bus import EventBus
from alerts.events import AlertChannel, AlertEventType, AlertPriority, TradingAlertEvent
from alerts.manager import AlertManager
from alerts.settings_store import NotificationSettingsStore, UserNotificationSettings

__all__ = [
    "AlertChannel",
    "AlertEventType",
    "AlertManager",
    "AlertPriority",
    "EventBus",
    "NotificationSettingsStore",
    "TradingAlertEvent",
    "UserNotificationSettings",
    "emit_daily_summary",
    "emit_execution_exit",
    "emit_kill_switch",
    "emit_order_lifecycle",
    "emit_risk_alert",
    "emit_signal_alerts",
]
