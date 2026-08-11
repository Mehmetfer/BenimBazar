from __future__ import annotations

import os

from alerts.channels.base import ChannelResult
from alerts.events import AlertChannel, TradingAlertEvent


class PushChannel:
    """Push abstraction. Without credentials → logged no-op (not a real delivery)."""

    name = "push_stub"
    channel = AlertChannel.PUSH

    def __init__(self) -> None:
        # Never log the actual secret values
        self.enabled = os.getenv("PUSH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        self.has_creds = bool(os.getenv("PUSH_SERVER_KEY") or os.getenv("FCM_SERVER_KEY"))
        self.provider_name = os.getenv("PUSH_PROVIDER", "none")

    def send(self, event: TradingAlertEvent) -> ChannelResult:
        body = event.payload.get("push_body") or event.message
        if not self.enabled or not self.has_creds:
            # Honest: not delivered to a real device
            return ChannelResult(
                True,
                self.channel,
                f"{self.provider_name}_noop",
                detail=f"push_skipped title={event.title} body_len={len(body)}",
            )
        # Real provider not wired — refuse to pretend success as delivered
        return ChannelResult(
            False,
            self.channel,
            self.provider_name,
            error="push_provider_not_implemented",
            detail="Credentials present but HTTP push adapter not implemented; trading unaffected.",
        )
