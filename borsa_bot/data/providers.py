"""Market data providers — honesty first. Simulated ≠ live.

HttpLiveProviderStub is a STUB (not REAL). It never HTTP-fetches and never
invents prices. Production fail-closed: stub → NO MARKET DATA → NO TRADE.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from typing import Protocol

from config.models import Bar, QuoteSnapshot
from data.contract import (
    BASE_TIMEFRAME,
    EnvironmentOrigin,
    INDEX_SYMBOL,
    REQUIRED_HISTORY_BARS_15M,
    check_history,
    normalize_app_symbol,
    stamp_bar_defaults,
    stamp_quote_defaults,
)
from data.integrity import (
    DataSourceKind,
    DataSourceMeta,
    build_source_meta,
)


UNIVERSE: dict[str, tuple[str, str, float]] = {
    "THYAO": ("Türk Hava Yolları", "ULASTIRMA", 312.5),
    "ASELS": ("Aselsan", "SAVUNMA", 78.4),
    "GARAN": ("Garanti BBVA", "BANKA", 118.2),
    "EREGL": ("Erdemir", "METAL", 54.75),
    "BIMAS": ("BİM", "PERAKENDE", 542.0),
    "AKBNK": ("Akbank", "BANKA", 64.3),
    "SAHOL": ("Sabancı Holding", "HOLDING", 98.1),
    "KCHOL": ("Koç Holding", "HOLDING", 186.4),
    "TUPRS": ("Tüpraş", "ENERJI", 168.9),
    "SISE": ("Şişecam", "SANAYI", 49.85),
    "XU100": ("BIST 100", "ENDEX", 10000.0),
}


class MarketDataProvider(Protocol):
    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]: ...
    def get_quote(self, symbol: str) -> QuoteSnapshot: ...
    def list_symbols(self) -> list[str]: ...
    def tick(self) -> None: ...
    def is_fresh(self, max_age_sec: float = 30.0) -> bool: ...
    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta: ...
    def has_market_data(self) -> bool: ...


class SimulatedProvider:
    """Paper-only OHLCV simulator. MUST NEVER be labeled as live BIST data."""

    provider_id = "simulated"
    kind = DataSourceKind.SIMULATED
    display_name = "SimulatedProvider (paper only)"
    is_stub = False
    is_real_provider = False

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._bars: dict[str, list[Bar]] = {}
        self._last_tick = datetime.now(timezone.utc)
        self._init_history()

    def _init_history(self) -> None:
        now = datetime.now(timezone.utc)
        for symbol, (_, _, base) in UNIVERSE.items():
            bars: list[Bar] = []
            price = base * (0.9 + self._rng.random() * 0.1)
            for i in range(REQUIRED_HISTORY_BARS_15M):
                drift = (self._rng.random() - 0.48) * (0.012 if symbol != INDEX_SYMBOL else 0.006)
                o = price
                c = max(0.5, o * (1 + drift))
                h = max(o, c) * (1 + self._rng.random() * 0.006)
                l = min(o, c) * (1 - self._rng.random() * 0.006)
                vol = 1_000_000 * (0.5 + self._rng.random())
                trades = int(800 + self._rng.random() * 2200)
                bar = Bar(
                    ts=now - timedelta(minutes=15 * (REQUIRED_HISTORY_BARS_15M - i)),
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(vol, 0),
                    trades=trades,
                    data_source_kind=DataSourceKind.SIMULATED.value,
                )
                stamp_bar_defaults(
                    bar,
                    provider=self.provider_id,
                    origin=EnvironmentOrigin.SIMULATED,
                    symbol=symbol,
                    timeframe=BASE_TIMEFRAME,
                )
                bars.append(bar)
                price = c
            self._bars[symbol] = bars

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        for symbol, bars in self._bars.items():
            last = bars[-1]
            scale = 0.01 if symbol != INDEX_SYMBOL else 0.004
            drift = (self._rng.random() - 0.5) * scale
            o = last.close
            c = max(0.5, o * (1 + drift))
            h = max(o, c) * (1 + self._rng.random() * 0.004)
            l = min(o, c) * (1 - self._rng.random() * 0.004)
            vol = last.volume * (0.8 + self._rng.random() * 0.5)
            bar = Bar(
                ts=now,
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=round(vol, 0),
                trades=int(700 + self._rng.random() * 2500),
                data_source_kind=DataSourceKind.SIMULATED.value,
            )
            stamp_bar_defaults(
                bar,
                provider=self.provider_id,
                origin=EnvironmentOrigin.SIMULATED,
                symbol=symbol,
                timeframe=BASE_TIMEFRAME,
            )
            bars.append(bar)
            if len(bars) > 300:
                del bars[0 : len(bars) - 300]
        self._last_tick = now

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        sym = normalize_app_symbol(symbol)
        return list(self._bars[sym][-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        sym = normalize_app_symbol(symbol)
        name, sector, _ = UNIVERSE[sym]
        bar = self._bars[sym][-1]
        spread = max(0.01, bar.close * 0.0008)
        ts = bar.ts if bar.ts.tzinfo else bar.ts.replace(tzinfo=timezone.utc)
        q = QuoteSnapshot(
            symbol=sym,
            name=name,
            sector=sector,
            price=bar.close,
            bid=round(bar.close - spread / 2, 2),
            ask=round(bar.close + spread / 2, 2),
            volume=bar.volume,
            trades=bar.trades,
            ts=ts,
            data_source_kind=DataSourceKind.SIMULATED.value,
        )
        return stamp_quote_defaults(q, provider=self.provider_id, origin=EnvironmentOrigin.SIMULATED)

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != INDEX_SYMBOL]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        age = (datetime.now(timezone.utc) - self._last_tick).total_seconds()
        return age <= max_age_sec

    def has_market_data(self) -> bool:
        return True

    def history_status(self, symbol: str = "THYAO") -> dict:
        bars = self.get_bars(symbol, lookback=REQUIRED_HISTORY_BARS_15M + 10)
        return check_history(bars).to_dict()

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self.kind,
            display_name=self.display_name,
            connected=True,
            last_update=self._last_tick,
            max_age_sec=max_age_sec,
            live_ready=False,
        )


class RequiredLiveProvider:
    """Fail-closed when credentials/URL missing. Never fabricates quotes/mock fallback."""

    provider_id = "live_required"
    kind = DataSourceKind.REQUIRED
    display_name = "Live market data (not configured)"
    is_stub = False
    is_real_provider = False

    def __init__(self, reason: str = "MARKET_DATA_URL / credentials missing") -> None:
        self.reason = reason
        self._last_attempt = datetime.now(timezone.utc)

    def tick(self) -> None:
        self._last_attempt = datetime.now(timezone.utc)

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return []

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        raise RuntimeError("NO_MARKET_DATA: canlı veri kaynağı yapılandırılmadı")

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != INDEX_SYMBOL]

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
            note=f"DATA SOURCE REQUIRED — {self.reason}",
        )


class HttpLiveProviderStub:
    """STUB — NOT a real BIST provider.

    Classification: STUB (not REAL, not MOCK).
    No HTTP request, no real prices/OHLCV. Never invents synthetic quotes.
    kind=REQUIRED until a real adapter replaces this. Not tradeable.
    """

    provider_id = "http_live_stub"
    kind = DataSourceKind.REQUIRED
    display_name = "HTTP Market Data API (STUB — not implemented)"
    is_stub = True
    is_real_provider = False

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._last_ok: datetime | None = None
        self._connected = False
        self._error = "LIVE_ADAPTER_NOT_IMPLEMENTED — STUB only; NO MARKET DATA"
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._bars: dict[str, list[Bar]] = {}

    def tick(self) -> None:
        self._connected = False
        if not self.base_url or not self.token:
            self._error = "missing_url_or_token"
        else:
            self._error = "LIVE_ADAPTER_NOT_IMPLEMENTED — gerçek endpoint bağlanana kadar VERİ YOK"

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return list(self._bars.get(normalize_app_symbol(symbol), [])[-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        q = self._quotes.get(normalize_app_symbol(symbol))
        if q is None:
            raise RuntimeError("NO_MARKET_DATA: stub has no live quotes")
        return q

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != INDEX_SYMBOL]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return False

    def has_market_data(self) -> bool:
        return False

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=DataSourceKind.REQUIRED,
            display_name=self.display_name,
            connected=False,
            last_update=None,
            max_age_sec=max_age_sec,
            live_ready=False,
            note=self._error,
        )


def create_provider(name: str = "simulated") -> MarketDataProvider:
    """Factory. PRODUCTION mock/sim HARD BLOCKED. live/bist/http → HttpLiveMarketDataProvider.

    broker → RequiredLiveProvider (BROKER ≠ market-data provider).
    HttpLiveProviderStub retained for tests / explicit stub use only.
    """
    from data.validation import (
        AppEnvironment,
        ProductionMarketDataViolation,
        gate_provider_selection,
        normalize_app_env,
    )
    from config.settings import settings as _settings

    env = normalize_app_env(getattr(_settings, "app_env", "DEVELOPMENT"))
    key = (name or "simulated").strip().lower()

    gate = gate_provider_selection(key, env)
    if not gate.ok:
        import logging

        logging.getLogger("borsa_bot.market_data").error(
            "Production market data rejected: simulated source name=%s code=%s",
            key,
            gate.code.value,
        )
        return RequiredLiveProvider(
            f"{gate.code.value}: Production rejects provider={key!r}. NO MARKET DATA."
        )

    if key in {"simulated", "sim", "paper", "mock", "demo", "fake", "synthetic", "dummy"}:
        if env == AppEnvironment.PRODUCTION:
            raise ProductionMarketDataViolation(
                f"PRODUCTION_MARKET_DATA_VIOLATION: provider={key}"
            )
        return SimulatedProvider()
    if key in {"required", "none", "off"}:
        return RequiredLiveProvider("DATA_PROVIDER=required — canlı kaynak bekleniyor")
    if key == "broker":
        return RequiredLiveProvider(
            "DATA_PROVIDER=broker rejected as market-data provider — BROKER source is SEPARATE"
        )
    if key in {"yahoo", "bist_yahoo", "yf", "yahoo_finance"}:
        from data.yahoo_bist import YahooBistMarketDataProvider

        provider = YahooBistMarketDataProvider()
        try:
            provider.tick()
        except Exception:  # noqa: BLE001
            pass
        return provider
    if key == "auto":
        from data.session_auto import SessionAutoBistProvider

        provider = SessionAutoBistProvider()
        try:
            provider.tick()
        except Exception:  # noqa: BLE001
            pass
        return provider
    if key in {"live", "bist", "http"}:
        url = os.getenv("MARKET_DATA_URL", "").strip()
        token = os.getenv("MARKET_DATA_TOKEN", "").strip()
        if not url or not token:
            return RequiredLiveProvider(
                "DATA_PROVIDER=live ancak MARKET_DATA_URL / MARKET_DATA_TOKEN yok"
            )
        from data.http_live import HttpLiveMarketDataProvider

        provider = HttpLiveMarketDataProvider(url, token)
        # Probe once — fail closed if unreachable (still returns provider; has_market_data=False)
        try:
            provider.tick()
        except Exception:  # noqa: BLE001
            pass
        if not provider.has_market_data():
            # Keep real provider instance (not stub) so readiness audits show REAL adapter present but disconnected
            return provider
        return provider
    if env == AppEnvironment.PRODUCTION:
        import logging

        logging.getLogger("borsa_bot.market_data").error(
            "Production market data rejected: unknown source name=%s", key
        )
        return RequiredLiveProvider(
            f"PRODUCTION_MARKET_DATA_VIOLATION / UNKNOWN_SOURCE: provider={key!r}"
        )
    raise ValueError(
        f"Unknown data provider: {name}. "
        "Use simulated | auto | yahoo | required | live (needs MARKET_DATA_URL + MARKET_DATA_TOKEN)."
    )


def classify_provider(provider: object) -> str:
    """REAL | STUB | MOCK — readiness audit helper."""
    from data.http_live import HttpLiveMarketDataProvider
    from data.session_auto import SessionAutoBistProvider
    from data.yahoo_bist import YahooBistMarketDataProvider

    if getattr(provider, "is_stub", False) or isinstance(provider, HttpLiveProviderStub):
        return "STUB"
    if isinstance(provider, (HttpLiveMarketDataProvider, YahooBistMarketDataProvider, SessionAutoBistProvider)):
        return "REAL"
    if getattr(provider, "kind", None) == DataSourceKind.SIMULATED:
        return "MOCK"
    if getattr(provider, "is_real_provider", False):
        return "REAL"
    if isinstance(provider, RequiredLiveProvider):
        return "STUB"
    return "STUB"
