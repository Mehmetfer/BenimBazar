"""Crypto provider factory — independent of data.providers.create_provider (BIST)."""

from __future__ import annotations

import os

from crypto.http_client import DEFAULT_API_BASE
from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.safety import is_mock_crypto_provider_name
from data.validation import AppEnvironment, normalize_app_env


def create_crypto_provider(
    name: str | None = None,
    *,
    crypto_enabled: bool | None = None,
    app_env: str | None = None,
    enable_websocket: bool | None = None,
) -> ParibuMarketDataProvider | RequiredCryptoProvider:
    """Build crypto MD provider. Never returns a price-inventing mock.

    PRODUCTION + mock name → RequiredCryptoProvider (fail closed).
    CRYPTO_ENABLED=false → RequiredCryptoProvider.
    paribu/live/http + PARIBU_ENABLED → live ParibuMarketDataProvider (public REST/WS).
    """
    from config.settings import settings

    enabled = settings.crypto_enabled if crypto_enabled is None else bool(crypto_enabled)
    env = normalize_app_env(app_env or settings.app_env)
    key = (name if name is not None else settings.crypto_provider).strip().lower()

    if not enabled:
        return RequiredCryptoProvider("CRYPTO_ENABLED=false — crypto plane off")

    if is_mock_crypto_provider_name(key):
        return RequiredCryptoProvider(
            f"PRODUCTION_MARKET_DATA_VIOLATION: crypto provider={key!r} rejected"
            if env == AppEnvironment.PRODUCTION
            else f"crypto mock provider={key!r} rejected — use live paribu (no invented prices)"
        )

    if key in {"", "required", "none", "off", "disabled"}:
        return RequiredCryptoProvider("CRYPTO_PROVIDER=required")

    if key in {"paribu", "live", "http", "crypto"}:
        if not settings.paribu_enabled:
            return RequiredCryptoProvider("PARIBU_ENABLED=false")
        api_base = (
            os.getenv("PARIBU_API_BASE", "").strip()
            or (settings.paribu_api_base or "").strip()
            or DEFAULT_API_BASE
        )
        ws = settings.paribu_ws_enabled if enable_websocket is None else bool(enable_websocket)
        return ParibuMarketDataProvider(
            api_base=api_base,
            api_key=os.getenv("PARIBU_API_KEY", settings.paribu_api_key),
            api_secret=os.getenv("PARIBU_API_SECRET", settings.paribu_api_secret),
            enable_websocket=ws,
            poll_interval_sec=float(getattr(settings, "paribu_poll_interval_sec", 3.0)),
        )

    if env == AppEnvironment.PRODUCTION:
        return RequiredCryptoProvider(
            f"PRODUCTION unknown crypto provider={key!r} — NO MARKET DATA"
        )
    raise ValueError(
        f"Unknown crypto provider: {name!r}. Use paribu | required (CRYPTO_ENABLED)."
    )
