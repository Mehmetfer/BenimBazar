"""Crypto foundation service — isolated from TradingService (BIST).

Phase 1: status + empty signals only. Does not call BIST strategy / BUY matrix.
"""

from __future__ import annotations

from typing import Any

from config.settings import settings
from crypto.market import MarketType
from crypto.providers.factory import create_crypto_provider
from crypto.safety import gate_crypto_provider
from data.validation import normalize_app_env


class CryptoFoundationService:
    """CRYPTO market plane entrypoint. BIST TradingService remains untouched."""

    def __init__(self) -> None:
        self.provider = create_crypto_provider()
        self.market_type = MarketType.CRYPTO
        self._gate = None

    def refresh_provider(self) -> None:
        self.provider = create_crypto_provider()

    def status(self) -> dict[str, Any]:
        gate = gate_crypto_provider(
            self.provider,
            app_env=settings.app_env,
            crypto_enabled=settings.crypto_enabled,
        )
        self._gate = gate
        meta = self.provider.source_meta(settings.data_freshness_sec)
        provenance = getattr(self.provider, "provenance", lambda: {})()
        return {
            "market_type": MarketType.CRYPTO.value,
            "crypto_enabled": settings.crypto_enabled,
            "paribu_enabled": settings.paribu_enabled,
            "crypto_provider": settings.crypto_provider,
            "provider_id": getattr(self.provider, "provider_id", ""),
            "provider_class": type(self.provider).__name__,
            "is_stub": bool(getattr(self.provider, "is_stub", False)),
            "has_market_data": bool(self.provider.has_market_data()),
            "signals_allowed": False,  # Phase 1 hard rule
            "tradeable": False,
            "live_trading": False,
            "data_source": meta.to_dict(),
            "provenance": provenance,
            "gate": gate.to_dict(),
            "symbols": list(self.provider.list_symbols()),
            "ui": {
                "title": "Kripto (Paribu)",
                "ready": False,
                "message": (
                    "CRYPTO foundation hazır · Paribu API henüz bağlı değil · "
                    "Sinyal/trade yok · BIST etkilenmez"
                    if settings.crypto_enabled
                    else "CRYPTO_ENABLED=false — kripto piyasası kapalı"
                ),
            },
            "app_env": normalize_app_env(settings.app_env).value,
        }

    def scan(self) -> list[dict[str, Any]]:
        """Phase 1: always empty — no crypto strategy yet."""
        _ = self.status()
        return []

    def markets_catalog(self) -> dict[str, Any]:
        """UI foundation: BIST + CRYPTO entries without mixing pipelines."""
        return {
            "markets": [
                {
                    "id": MarketType.BIST.value,
                    "label": "BIST",
                    "enabled": True,
                    "default": True,
                    "path": "/api/daily",
                },
                {
                    "id": MarketType.CRYPTO.value,
                    "label": "CRYPTO",
                    "enabled": bool(settings.crypto_enabled),
                    "default": False,
                    "path": "/api/crypto/status",
                    "ready": False,
                },
            ],
            "active_default": MarketType.BIST.value,
        }
