"""Notification channel readiness status — honest ENABLED/DISABLED/NOT_CONFIGURED/ERROR."""

from __future__ import annotations

import os
from typing import Any

from config.settings import settings


def channel_status_report() -> dict[str, Any]:
    push_on = bool(getattr(settings, "push_on", False) or getattr(settings, "push_enabled", False))
    push_creds = bool(os.getenv("PUSH_SERVER_KEY") or os.getenv("FCM_SERVER_KEY"))
    if not push_on:
        push = "DISABLED"
    elif not push_creds:
        push = "NOT_CONFIGURED"
    else:
        push = "ERROR"  # creds present but HTTP adapter not implemented

    sms_on = bool(getattr(settings, "sms_on", False))
    sms_provider = (os.getenv("SMS_PROVIDER") or getattr(settings, "sms_provider", "null") or "null").lower()
    if not sms_on:
        sms = "DISABLED"
    elif sms_provider in {"", "null", "none"}:
        sms = "NOT_CONFIGURED"
    elif sms_provider in {"log_only"}:
        sms = "ENABLED"  # intentional non-network
    else:
        # Http stub → not real delivery
        sms = "ERROR"

    sound = "ENABLED" if getattr(settings, "sound_on", True) else "DISABLED"
    tts = "ENABLED" if getattr(settings, "tts_on", True) else "DISABLED"
    in_app = "ENABLED"

    return {
        "channels": {
            "PUSH": push,
            "SOUND": sound,
            "TTS": tts,
            "SMS": sms,
            "IN_APP": in_app,
        },
        "note": "ENABLED means channel path is active — not a guarantee of external carrier delivery. "
        "NOT_CONFIGURED / ERROR must not be shown as successfully delivered.",
        "placeholders_are_not_deliveries": True,
    }
