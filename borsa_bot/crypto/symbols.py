"""Crypto symbol mapping — app symbols vs provider-native formats.

Do NOT assume Paribu wire format until a real adapter is connected.
Strategy / UI / DB should use application symbols only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CryptoSymbolRef:
    """Canonical crypto identity inside the application."""

    app_symbol: str  # e.g. BTC_USDT (normalized)
    base: str  # BTC
    quote: str  # USDT
    display: str  # BTC/USDT
    market_type: str = "CRYPTO"


def normalize_crypto_app_symbol(raw: str | None) -> str:
    """Provider / UI variants → application symbol (BASE_QUOTE).

    Accepts: BTC/USDT, BTC-USDT, BTC_USDT, btcusdt (best-effort split).
    Does not invent Paribu-specific ids.
    """
    if not raw:
        return ""
    s = str(raw).strip().upper()
    for prefix in ("PARIBU:", "CRYPTO:", "SPOT:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    s = s.replace(" ", "")
    if "/" in s:
        base, _, quote = s.partition("/")
        return f"{base}_{quote}" if base and quote else s.replace("/", "_")
    if "-" in s:
        base, _, quote = s.partition("-")
        return f"{base}_{quote}" if base and quote else s.replace("-", "_")
    if "_" in s:
        return s
    # Ambiguous concatenated forms — leave as-is until provider map exists
    return s


def to_display_symbol(app_symbol: str) -> str:
    sym = normalize_crypto_app_symbol(app_symbol)
    if "_" in sym:
        base, _, quote = sym.partition("_")
        return f"{base}/{quote}" if quote else sym
    return sym


def parse_crypto_symbol(raw: str | None) -> CryptoSymbolRef | None:
    app = normalize_crypto_app_symbol(raw)
    if not app or "_" not in app:
        return None
    base, _, quote = app.partition("_")
    if not base or not quote:
        return None
    return CryptoSymbolRef(
        app_symbol=app,
        base=base,
        quote=quote,
        display=f"{base}/{quote}",
        market_type="CRYPTO",
    )


class CryptoSymbolMapper:
    """Bidirectional map between app symbols and provider-native ids.

    Empty until a real Paribu (or other) adapter registers mappings.
    Unknown provider symbols never silently become BIST tickers.
    """

    def __init__(self, provider_id: str = "paribu") -> None:
        self.provider_id = provider_id
        self._app_to_provider: dict[str, str] = {}
        self._provider_to_app: dict[str, str] = {}

    def register(self, app_symbol: str, provider_symbol: str) -> None:
        app = normalize_crypto_app_symbol(app_symbol)
        prov = str(provider_symbol).strip()
        if not app or not prov:
            raise ValueError("app_symbol and provider_symbol required")
        self._app_to_provider[app] = prov
        self._provider_to_app[prov] = app
        self._provider_to_app[prov.upper()] = app

    def to_provider(self, app_symbol: str) -> str | None:
        """None until mapping registered — callers must not invent wire format."""
        return self._app_to_provider.get(normalize_crypto_app_symbol(app_symbol))

    def to_app(self, provider_symbol: str) -> str | None:
        key = str(provider_symbol).strip()
        return self._provider_to_app.get(key) or self._provider_to_app.get(key.upper())

    def known_app_symbols(self) -> list[str]:
        return sorted(self._app_to_provider.keys())
