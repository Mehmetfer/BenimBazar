from __future__ import annotations

from alerts.channels.base import ChannelResult
from alerts.events import AlertChannel, TradingAlertEvent


class SoundChannel:
    """Records sound intent for clients (Web Audio / mobile). Server does not play audio."""

    name = "sound_intent"
    channel = AlertChannel.SOUND

    def send(self, event: TradingAlertEvent) -> ChannelResult:
        profile = event.resolved_sound().value
        return ChannelResult(
            True,
            self.channel,
            self.name,
            detail=f"sound_profile={profile}",
        )
