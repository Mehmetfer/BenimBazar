from __future__ import annotations

import json

from alerts.channels.base import ChannelResult
from alerts.events import AlertChannel, TradingAlertEvent
from alerts.log import NotificationLog


class InAppChannel:
    """Application inbox — always local, never affects trading."""

    name = "in_app"
    channel = AlertChannel.IN_APP

    def __init__(self, log: NotificationLog) -> None:
        self.log = log

    def send(self, event: TradingAlertEvent) -> ChannelResult:
        try:
            self.log.write_in_app(
                event_id=event.event_id,
                symbol=event.symbol,
                event_type=event.event_type.value,
                priority=event.resolved_priority().value,
                title=event.title,
                message=event.message,
                sound_profile=event.resolved_sound().value,
                tts_text=event.tts_text,
                payload_json=json.dumps(event.payload, default=str),
                timestamp=event.timestamp,
            )
            return ChannelResult(True, self.channel, self.name)
        except Exception as exc:  # noqa: BLE001
            return ChannelResult(False, self.channel, self.name, error=str(exc))
