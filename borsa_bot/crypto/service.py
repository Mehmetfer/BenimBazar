"""Crypto foundation service — isolated from TradingService (BIST).

Phase 2: live Paribu quotes/discovery when enabled; signals/trading still off.
"""

from __future__ import annotations

from typing import Any

from config.settings import settings
from crypto.backfill import backfill_symbol
from crypto.market import MarketType
from crypto.providers.factory import create_crypto_provider
from crypto.providers.paribu import ParibuMarketDataProvider
from crypto.safety import gate_crypto_provider
from data.validation import normalize_app_env


class CryptoFoundationService:
    """CRYPTO market plane entrypoint. BIST TradingService remains untouched."""

    def __init__(self) -> None:
        self.provider = create_crypto_provider()
        self.market_type = MarketType.CRYPTO
        self._gate = None

    def refresh_provider(self) -> None:
        old = self.provider
        self.provider = create_crypto_provider()
        close = getattr(old, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    def status(self) -> dict[str, Any]:
        gate = gate_crypto_provider(
            self.provider,
            app_env=settings.app_env,
            crypto_enabled=settings.crypto_enabled,
        )
        self._gate = gate
        meta = self.provider.source_meta(settings.data_freshness_sec)
        provenance = getattr(self.provider, "provenance", lambda: {})()
        symbols = list(self.provider.list_symbols()) if settings.crypto_enabled else []
        sample_quotes: list[dict[str, Any]] = []
        if isinstance(self.provider, ParibuMarketDataProvider) and self.provider.has_market_data():
            for sym in symbols[:5]:
                try:
                    q = self.provider.get_quote(sym)
                    sample_quotes.append(
                        {
                            "symbol": q.symbol,
                            "display": q.name,
                            "price": q.price,
                            "bid": q.bid,
                            "ask": q.ask,
                            "spread_pct": q.spread_pct,
                            "volume": q.volume,
                            "ts": q.ts.isoformat() if q.ts else None,
                            "market_type": MarketType.CRYPTO.value,
                            "data_source_kind": q.data_source_kind,
                            "provider": q.provider,
                            "market_status": q.market_status,
                        }
                    )
                except Exception:  # noqa: BLE001
                    continue
        return {
            "market_type": MarketType.CRYPTO.value,
            "crypto_enabled": settings.crypto_enabled,
            "paribu_enabled": settings.paribu_enabled,
            "crypto_provider": settings.crypto_provider,
            "provider_id": getattr(self.provider, "provider_id", ""),
            "provider_class": type(self.provider).__name__,
            "is_stub": bool(getattr(self.provider, "is_stub", False)),
            "is_real_provider": bool(getattr(self.provider, "is_real_provider", False)),
            "has_market_data": bool(self.provider.has_market_data()),
            "signals_allowed": False,  # Phase 2: MD only — no crypto strategy yet
            "tradeable": False,
            "live_trading": False,
            "data_source": meta.to_dict(),
            "provenance": provenance,
            "gate": gate.to_dict(),
            "symbols": symbols,
            "symbol_count": len(symbols),
            "sample_quotes": sample_quotes,
            "websocket": (getattr(self.provider, "status_dict", lambda: {})() or {}).get("websocket"),
            "ui": {
                "title": "Kripto (Paribu)",
                "ready": bool(self.provider.has_market_data()),
                "message": (
                    f"Paribu LIVE · {len(symbols)} markets · signals/trading KAPALI · BIST etkilenmez"
                    if self.provider.has_market_data()
                    else (
                        "CRYPTO_ENABLED=false — kripto piyasası kapalı"
                        if not settings.crypto_enabled
                        else "Paribu bağlı değil veya veri yok"
                    )
                ),
            },
            "app_env": normalize_app_env(settings.app_env).value,
            "docs": "crypto/docs/PARIBU_API.md",
        }

    def scan(self) -> list[dict[str, Any]]:
        """Phase 2: always empty — crypto analysis/strategy is Phase 3."""
        _ = self.status()
        return []

    def backfill(self, symbol: str, timeframe: str = "15m") -> dict[str, Any]:
        if not isinstance(self.provider, ParibuMarketDataProvider):
            return {"ok": False, "note": "live Paribu provider required", "symbol": symbol}
        return backfill_symbol(self.provider, symbol, timeframe=timeframe).to_dict()

    def markets_catalog(self) -> dict[str, Any]:
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
                    "ready": bool(settings.crypto_enabled and settings.paribu_enabled),
                },
            ],
            "active_default": MarketType.BIST.value,
        }
