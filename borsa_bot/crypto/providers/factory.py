"""Crypto provider factory — independent of data.providers.create_provider (BIST)."""

from __future__ import annotations

import os

from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.safety import is_mock_crypto_provider_name
from data.validation import AppEnvironment, normalize_app_env


def create_crypto_provider(
    name: str | None = None,
    *,
    crypto_enabled: bool | None = None,
    app_env: str | None = None,
) -> ParibuMarketDataProvider | RequiredCryptoProvider:
    """Build crypto MD provider. Never returns a price-inventing mock.

    PRODUCTION + mock name → RequiredCryptoProvider (fail closed).
    CRYPTO_ENABLED=false → RequiredCryptoProvider.
    paribu/live/http → ParibuMarketDataProvider STUB (no HTTP).
    """
    from config.settings import settings

    enabled = settings.crypto_enabled if crypto_enabled is None else bool(crypto_enabled)
    env = normalize_app_env(app_env or settings.app_env)
    key = (name if name is not None else settings.crypto_provider).strip().lower()

    if not enabled:
        return RequiredCryptoProvider("CRYPTO_ENABLED=false — crypto plane off")

    if is_mock_crypto_provider_name(key):
        if env == AppEnvironment.PRODUCTION:
            return RequiredCryptoProvider(
                f"PRODUCTION_MARKET_DATA_VIOLATION: crypto provider={key!r} rejected"
            )
        # Even in DEV: Phase 1 does not ship a crypto price simulator into the trading plane.
        return RequiredCryptoProvider(
            f"crypto mock provider={key!r} not available — use paribu stub (no invented prices)"
        )

    if key in {"", "required", "none", "off", "disabled"}:
        return RequiredCryptoProvider("CRYPTO_PROVIDER=required")

    if key in {"paribu", "live", "http", "crypto"}:
        if not settings.paribu_enabled and key == "paribu":
            # CRYPTO_ENABLED may be true while PARIBU_ENABLED is false
            return RequiredCryptoProvider("PARIBU_ENABLED=false")
        return ParibuMarketDataProvider(
            api_base=os.getenv("PARIBU_API_BASE", settings.paribu_api_base),
            api_key=os.getenv("PARIBU_API_KEY", settings.paribu_api_key),
            api_secret=os.getenv("PARIBU_API_SECRET", settings.paribu_api_secret),
        )

    if env == AppEnvironment.PRODUCTION:
        return RequiredCryptoProvider(
            f"PRODUCTION unknown crypto provider={key!r} — NO MARKET DATA"
        )
    raise ValueError(
        f"Unknown crypto provider: {name!r}. Use paribu | required (CRYPTO_ENABLED)."
    )
