"""Crypto provider factory — independent of data.providers.create_provider (BIST).

Default live path uses public CEX REST venues that open-source bots pull via CCXT
(OKX → Gate → Kraken). Paribu remains optional when PARIBU_ENABLED=true.
"""

from __future__ import annotations

import os
from typing import Any

from crypto.http_client import DEFAULT_API_BASE
from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.providers.public_exchanges import (
    FailoverCryptoProvider,
    build_failover_chain,
    build_public_provider,
)
from crypto.safety import is_mock_crypto_provider_name
from data.validation import AppEnvironment, normalize_app_env

_PUBLIC_KEYS = frozenset(
    {
        "auto",
        "public",
        "ccxt",
        "okx",
        "okex",
        "gate",
        "gateio",
        "gate_io",
        "kraken",
        "failover",
    }
)


def _failover_names_from_settings() -> list[str]:
    from config.settings import settings

    raw = (getattr(settings, "crypto_failover", None) or os.getenv("CRYPTO_FAILOVER", "") or "").strip()
    if raw:
        return [p.strip().lower() for p in raw.split(",") if p.strip()]
    return ["okx", "gate", "kraken"]


def create_crypto_provider(
    name: str | None = None,
    *,
    crypto_enabled: bool | None = None,
    app_env: str | None = None,
    enable_websocket: bool | None = None,
) -> Any:
    """Build crypto MD provider. Never returns a price-inventing mock.

    CRYPTO_PROVIDER=
      auto|public|ccxt|failover → OKX→Gate→Kraken public REST (+ Paribu if enabled)
      okx|gate|kraken           → single public venue
      paribu|live|http          → Paribu when PARIBU_ENABLED
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
            else f"crypto mock provider={key!r} rejected — use auto/okx/gate/kraken/paribu (no invented prices)"
        )

    if key in {"", "required", "none", "off", "disabled"}:
        return RequiredCryptoProvider("CRYPTO_PROVIDER=required")

    # Public multi-venue (GitHub/ccxt-style sources)
    if key in {"auto", "public", "ccxt", "failover"}:
        chain = build_failover_chain(_failover_names_from_settings())
        if settings.paribu_enabled:
            try:
                chain._providers.append(  # noqa: SLF001 — intentional append for optional Paribu
                    ParibuMarketDataProvider(
                        api_base=(
                            os.getenv("PARIBU_API_BASE", "").strip()
                            or (settings.paribu_api_base or "").strip()
                            or DEFAULT_API_BASE
                        ),
                        api_key=os.getenv("PARIBU_API_KEY", settings.paribu_api_key),
                        api_secret=os.getenv("PARIBU_API_SECRET", settings.paribu_api_secret),
                        enable_websocket=settings.paribu_ws_enabled if enable_websocket is None else bool(enable_websocket),
                        poll_interval_sec=float(getattr(settings, "paribu_poll_interval_sec", 3.0)),
                    )
                )
            except Exception:  # noqa: BLE001
                pass
        chain.tick()
        if chain.has_market_data():
            return chain
        return RequiredCryptoProvider(f"public failover exhausted: {chain._last_error}")  # noqa: SLF001

    if key in {"okx", "okex", "gate", "gateio", "gate_io", "kraken"}:
        try:
            p = build_public_provider(key)
            p.tick()
            if p.has_market_data():
                return p
            return RequiredCryptoProvider(f"{key} public MD unavailable: {getattr(p, '_error', '')}")
        except Exception as exc:  # noqa: BLE001
            return RequiredCryptoProvider(f"{key} public MD error: {exc}")

    if key in {"paribu", "live", "http", "crypto"}:
        if not settings.paribu_enabled:
            # Fall back to public venues instead of hard-requiring Paribu
            chain = build_failover_chain(_failover_names_from_settings())
            chain.tick()
            if chain.has_market_data():
                return chain
            return RequiredCryptoProvider("PARIBU_ENABLED=false and public failover failed")
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
        f"Unknown crypto provider: {name!r}. Use auto|okx|gate|kraken|paribu|required."
    )


def is_live_crypto_provider(provider: Any) -> bool:
    """Duck-type live crypto MD (Paribu or public CEX) — not RequiredCryptoProvider."""
    if provider is None:
        return False
    if isinstance(provider, RequiredCryptoProvider):
        return False
    return bool(getattr(provider, "is_real_provider", False))
