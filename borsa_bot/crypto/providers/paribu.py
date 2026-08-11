"""Paribu market-data provider — Phase 1 STUB only.

Implements MarketDataProvider protocol shape without HTTP / API keys / prices.
Never invents OHLCV. Production fail-closed via crypto.safety.
"""

from __future__ import annotations

from datetime import datetime, timezone

from config.models import Bar, QuoteSnapshot
from crypto.market import MarketType
from crypto.safety import crypto_provenance_fields
from crypto.symbols import CryptoSymbolMapper, normalize_crypto_app_symbol
from data.integrity import DataSourceKind, DataSourceMeta, build_source_meta


class RequiredCryptoProvider:
    """Fail-closed placeholder when crypto is disabled or misconfigured."""

    provider_id = "crypto_required"
    kind = DataSourceKind.REQUIRED
    display_name = "Crypto market data (not configured)"
    is_stub = False
    is_real_provider = False
    market_type = MarketType.CRYPTO

    def __init__(self, reason: str = "CRYPTO_ENABLED=false or provider missing") -> None:
        self.reason = reason

    def tick(self) -> None:
        return None

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return []

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        raise RuntimeError(f"NO_MARKET_DATA: {self.reason}")

    def list_symbols(self) -> list[str]:
        return []

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return False

    def has_market_data(self) -> bool:
        return False

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self.kind,
            display_name=self.display_name,
            connected=False,
            last_update=None,
            max_age_sec=max_age_sec,
            live_ready=False,
            note=f"CRYPTO · {self.reason}",
        )

    def provenance(self) -> dict[str, str]:
        return crypto_provenance_fields(
            provider_id=self.provider_id,
            data_source_kind=self.kind,
        )


class ParibuMarketDataProvider:
    """Paribu adapter seam — STUB (not REAL, not MOCK prices).

    Classification: STUB
    - No HTTP request
    - No real endpoint / price / OHLCV
    - kind=REQUIRED until live adapter replaces this
    - list_symbols empty until real instrument discovery
    """

    provider_id = "paribu"
    kind = DataSourceKind.REQUIRED
    display_name = "Paribu (STUB — not connected)"
    is_stub = True
    is_real_provider = False
    market_type = MarketType.CRYPTO

    def __init__(
        self,
        *,
        api_base: str = "",
        api_key: str = "",
        api_secret: str = "",
        mapper: CryptoSymbolMapper | None = None,
    ) -> None:
        self.api_base = (api_base or "").rstrip("/")
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.mapper = mapper or CryptoSymbolMapper(provider_id=self.provider_id)
        self._connected = False
        self._error = "PARIBU_ADAPTER_NOT_IMPLEMENTED — STUB only; NO MARKET DATA"
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._bars: dict[str, list[Bar]] = {}

    def tick(self) -> None:
        self._connected = False
        if not self.api_base:
            self._error = "PARIBU_API_BASE missing — NO MARKET DATA"
        elif not self.api_key:
            # Key optional for public market data later; still stub in Phase 1
            self._error = "PARIBU_ADAPTER_NOT_IMPLEMENTED — gerçek endpoint bağlanana kadar VERİ YOK"
        else:
            self._error = "PARIBU_ADAPTER_NOT_IMPLEMENTED — NO HTTP in Phase 1"

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        key = normalize_crypto_app_symbol(symbol)
        return list(self._bars.get(key, [])[-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        key = normalize_crypto_app_symbol(symbol)
        q = self._quotes.get(key)
        if q is None:
            raise RuntimeError("NO_MARKET_DATA: Paribu stub has no live quotes")
        return q

    def list_symbols(self) -> list[str]:
        # Empty until real Paribu instrument list is wired (do not hardcode pairs)
        return list(self.mapper.known_app_symbols())

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return False

    def has_market_data(self) -> bool:
        return False

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self.kind,
            display_name=self.display_name,
            connected=False,
            last_update=None,
            max_age_sec=max_age_sec,
            live_ready=False,
            note=self._error,
        )

    def provenance(self) -> dict[str, str]:
        return crypto_provenance_fields(
            provider_id=self.provider_id,
            data_source_kind=self.kind,
        )

    def status_dict(self) -> dict:
        meta = self.source_meta()
        d = meta.to_dict()
        d.update(self.provenance())
        d["stub"] = True
        d["real_provider"] = False
        d["http_connected"] = False
        d["symbols"] = self.list_symbols()
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        return d
