from __future__ import annotations

import os
from typing import Protocol

from alerts.channels.base import ChannelResult
from alerts.events import AlertChannel, TradingAlertEvent


class SmsProvider(Protocol):
    """Provider-independent SMS interface. Implementations must not raise into trading."""

    name: str

    def send_sms(self, to: str, body: str) -> tuple[bool, str | None]:
        """Return (ok, error). Never include API keys in error strings."""
        ...


class NullSmsProvider:
    """Default when SMS is off or unconfigured — honest no-op."""

    name = "null"

    def send_sms(self, to: str, body: str) -> tuple[bool, str | None]:
        return True, None  # no-op success (not a real SMS)


class LogOnlySmsProvider:
    """Development provider: pretends attempt without network."""

    name = "log_only"

    def send_sms(self, to: str, body: str) -> tuple[bool, str | None]:
        if not to:
            return False, "missing_sms_to"
        return True, None


class HttpSmsProviderStub:
    """Config-driven stub. Does not call real APIs until adapter is implemented.

    Env:
      SMS_PROVIDER=http_stub
      SMS_API_URL=...
      SMS_API_KEY=... (never logged)
      SMS_FROM=...
      SMS_TO=...
    """

    name = "http_stub"

    def send_sms(self, to: str, body: str) -> tuple[bool, str | None]:
        url = os.getenv("SMS_API_URL", "").strip()
        key = os.getenv("SMS_API_KEY", "").strip()
        if not url or not key:
            return False, "sms_credentials_missing"
        # Honest: HTTP client not implemented — do not fake delivery
        return False, "sms_http_adapter_not_implemented"


def build_sms_provider() -> SmsProvider:
    kind = os.getenv("SMS_PROVIDER", "null").lower().strip()
    if kind in {"null", "none", ""}:
        return NullSmsProvider()
    if kind in {"log", "log_only"}:
        return LogOnlySmsProvider()
    if kind in {"http", "http_stub"}:
        return HttpSmsProviderStub()
    return NullSmsProvider()


class SmsChannel:
    name = "sms"
    channel = AlertChannel.SMS

    def __init__(self, provider: SmsProvider | None = None) -> None:
        self.provider = provider or build_sms_provider()
        self.to = os.getenv("SMS_TO", "").strip()

    def send(self, event: TradingAlertEvent) -> ChannelResult:
        # Prefer short ASCII SMS body for trade plans
        body = (event.payload.get("sms_ascii") or event.payload.get("sms_body") or event.message)[:160]
        if self.provider.name == "null":
            return ChannelResult(
                False,
                self.channel,
                self.provider.name,
                error="sms_not_configured",
                detail="SMS_ON may be true but SMS_PROVIDER=null — no real SMS sent",
            )
        try:
            ok, err = self.provider.send_sms(self.to, body)
            return ChannelResult(ok, self.channel, self.provider.name, error=err)
        except Exception as exc:  # noqa: BLE001 — never break trading
            return ChannelResult(False, self.channel, self.provider.name, error=type(exc).__name__)
