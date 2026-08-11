from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from alerts.events import AlertChannel, TradingAlertEvent


@dataclass
class ChannelResult:
    ok: bool
    channel: AlertChannel
    provider: str
    error: str | None = None
    detail: str | None = None


class NotificationChannel(Protocol):
    name: str
    channel: AlertChannel

    def send(self, event: TradingAlertEvent) -> ChannelResult: ...
