"""Live broker adapter factory — foundation only; real money stays OFF by default.

Adapters registered here are never selected unless LIVE_BROKER_ENABLED=true
AND LIVE_BROKER_ADAPTER names a known implementation. Unknown / empty → disabled.
"""

from __future__ import annotations

from typing import Any

from config.settings import settings
from execution.broker_adapter import BrokerAdapter, LiveBrokerDisabled


# Reserved adapter ids for future venues (not implemented → still disabled).
KNOWN_ADAPTER_IDS = frozenset(
    {
        "disabled",
        "none",
        "stub",
        # Future: "matriks", "info_yatirim", "gedik", "ibkr", "custom_http"
    }
)


def resolve_live_adapter(*, force_disabled: bool = False) -> BrokerAdapter:
    """Return the live adapter for ExecutionRouter.

    Default and fail-closed path: LiveBrokerDisabled.
    When a real venue adapter is added later, gate it behind:
      LIVE_BROKER_ENABLED=true
      LIVE_BROKER_ADAPTER=<id>
      LIVE_CONFIRMED=true (if confirmation required)
    """
    if force_disabled:
        return LiveBrokerDisabled()

    enabled = bool(getattr(settings, "live_broker_enabled", False))
    adapter_id = str(getattr(settings, "live_broker_adapter", "") or "disabled").strip().lower()

    if not enabled:
        return LiveBrokerDisabled(name="LiveBrokerDisabled")

    if adapter_id in {"", "disabled", "none", "stub"}:
        return LiveBrokerDisabled(
            name="LiveBrokerDisabled(enabled_flag_but_no_adapter)",
        )

    # Future venue adapters plug in here. Until then → disabled.
    # Example:
    #   if adapter_id == "custom_http":
    #       return CustomHttpLiveBroker(...)
    return LiveBrokerDisabled(
        name=f"LiveBrokerDisabled(unknown_adapter:{adapter_id})",
    )


def live_adapter_status() -> dict[str, Any]:
    adapter = resolve_live_adapter()
    enabled = bool(getattr(settings, "live_broker_enabled", False))
    confirmed = bool(getattr(settings, "live_confirmed", False))
    adapter_id = str(getattr(settings, "live_broker_adapter", "") or "disabled")
    dry_run = bool(getattr(settings, "live_dry_run", True))
    real = not isinstance(adapter, LiveBrokerDisabled) and not str(adapter.name).startswith("LiveBrokerDisabled")
    return {
        "adapter_name": getattr(adapter, "name", type(adapter).__name__),
        "adapter_id": adapter_id,
        "live_broker_enabled": enabled,
        "live_confirmed": confirmed,
        "live_dry_run": dry_run,
        "real_adapter_loaded": real,
        "known_adapter_ids": sorted(KNOWN_ADAPTER_IDS),
        "note": "Foundation only — no real money path until a venue adapter is implemented and unlocked",
    }
