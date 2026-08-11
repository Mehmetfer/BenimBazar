from __future__ import annotations

from alerts.channels.base import ChannelResult
from alerts.events import AlertChannel, TradingAlertEvent


class TtsChannel:
    """Produces Turkish TTS text for client speechSynthesis / mobile TTS.

    Server-side cloud TTS is optional and not claimed available without credentials.
    """

    name = "tts_tr"
    channel = AlertChannel.TTS
    language = "tr-TR"

    def send(self, event: TradingAlertEvent) -> ChannelResult:
        text = event.tts_text or event.message
        if not text:
            return ChannelResult(False, self.channel, self.name, error="empty_tts_text")
        return ChannelResult(
            True,
            self.channel,
            self.name,
            detail=f"lang={self.language}; text_len={len(text)}",
        )
