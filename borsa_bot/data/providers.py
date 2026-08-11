"""Market data providers — honesty first. Simulated ≠ live."""

from __future__ import annotations

import math
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Protocol

from config.models import Bar, QuoteSnapshot
from data.integrity import (
    DataSourceKind,
    DataSourceMeta,
    FreshnessStatus,
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
            for i in range(240):
                drift = (self._rng.random() - 0.48) * (0.012 if symbol != "XU100" else 0.006)
                o = price
                c = max(0.5, o * (1 + drift))
                h = max(o, c) * (1 + self._rng.random() * 0.006)
                l = min(o, c) * (1 - self._rng.random() * 0.006)
                vol = 1_000_000 * (0.5 + self._rng.random())
                trades = int(800 + self._rng.random() * 2200)
                bars.append(
                    Bar(
                        ts=now - timedelta(minutes=15 * (240 - i)),
                        open=round(o, 2),
                        high=round(h, 2),
                        low=round(l, 2),
                        close=round(c, 2),
                        volume=round(vol, 0),
                        trades=trades,
                        data_source_kind=DataSourceKind.SIMULATED.value,
                    )
                )
                price = c
            self._bars[symbol] = bars

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        for symbol, bars in self._bars.items():
            last = bars[-1]
            scale = 0.01 if symbol != "XU100" else 0.004
            drift = (self._rng.random() - 0.5) * scale
            o = last.close
            c = max(0.5, o * (1 + drift))
            h = max(o, c) * (1 + self._rng.random() * 0.004)
            l = min(o, c) * (1 - self._rng.random() * 0.004)
            vol = last.volume * (0.8 + self._rng.random() * 0.5)
            bars.append(
                Bar(
                    ts=now,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(vol, 0),
                    trades=int(700 + self._rng.random() * 2500),
                    data_source_kind=DataSourceKind.SIMULATED.value,
                )
            )
            if len(bars) > 300:
                del bars[0 : len(bars) - 300]
        self._last_tick = now

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return list(self._bars[symbol][-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        name, sector, _ = UNIVERSE[symbol]
        bar = self._bars[symbol][-1]
        spread = max(0.01, bar.close * 0.0008)
        return QuoteSnapshot(
            symbol=symbol,
            name=name,
            sector=sector,
            price=bar.close,
            bid=round(bar.close - spread / 2, 2),
            ask=round(bar.close + spread / 2, 2),
            volume=bar.volume,
            trades=bar.trades,
            ts=bar.ts,
            data_source_kind=DataSourceKind.SIMULATED.value,
        )

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != "XU100"]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        age = (datetime.now(timezone.utc) - self._last_tick).total_seconds()
        return age <= max_age_sec

    def has_market_data(self) -> bool:
        return True

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
    """Fail-closed live provider when credentials/URL are missing.

    Returns no prices — UI must show VERİ YOK / DATA SOURCE REQUIRED.
    Never fabricates quotes.
    """

    provider_id = "live_required"
    kind = DataSourceKind.REQUIRED
    display_name = "Live market data (not configured)"

    def __init__(self, reason: str = "MARKET_DATA_URL / credentials missing") -> None:
        self.reason = reason
        self._last_attempt = datetime.now(timezone.utc)

    def tick(self) -> None:
        self._last_attempt = datetime.now(timezone.utc)

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return []

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        # Honest empty quote — price None is not available on QuoteSnapshot (float).
        # Callers must check has_market_data() / source_meta before using price.
        raise RuntimeError("NO_MARKET_DATA: canlı veri kaynağı yapılandırılmadı")

    def list_symbols(self) -> list[str]:
        # Universe list for search UI only — not prices
        return [s for s in UNIVERSE if s != "XU100"]

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
    """Skeleton for a licensed HTTP market-data API.

    Without MARKET_DATA_URL + MARKET_DATA_TOKEN this stays disconnected and
    never invents prices. When configured, fetch must succeed or report NO_DATA.
    """

    provider_id = "http_live"
    kind = DataSourceKind.LIVE
    display_name = "HTTP Market Data API"

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._last_ok: datetime | None = None
        self._connected = False
        self._error = "not_fetched_yet"
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._bars: dict[str, list[Bar]] = {}

    def tick(self) -> None:
        # Real fetch would go here. Without a working endpoint, stay disconnected.
        # Do NOT fall back to simulated prices.
        if not self.base_url or not self.token:
            self._connected = False
            self._error = "missing_url_or_token"
            return
        # Placeholder: no fabricated response parsing — require real HTTP success later.
        self._connected = False
        self._error = "LIVE_ADAPTER_NOT_IMPLEMENTED — gerçek endpoint bağlanana kadar VERİ YOK"

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return list(self._bars.get(symbol, [])[-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        q = self._quotes.get(symbol)
        if q is None:
            raise RuntimeError("NO_MARKET_DATA: canlı kotasyon yok")
        return q

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != "XU100"]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        if not self._last_ok:
            return False
        return (datetime.now(timezone.utc) - self._last_ok).total_seconds() <= max_age_sec

    def has_market_data(self) -> bool:
        return self._connected and bool(self._quotes)

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        kind = DataSourceKind.LIVE if self._connected else DataSourceKind.REQUIRED
        return build_source_meta(
            provider_id=self.provider_id,
            kind=kind,
            display_name=self.display_name,
            connected=self._connected,
            last_update=self._last_ok,
            max_age_sec=max_age_sec,
            live_ready=False,
            note=self._error,
        )


def create_provider(name: str = "simulated") -> MarketDataProvider:
    """Factory. Unknown/live without credentials → RequiredLiveProvider (no fake prices).

    PRODUCTION: mock/simulated/demo/fake provider names are HARD BLOCKED
    (PRODUCTION_MARKET_DATA_VIOLATION) — fail closed to RequiredLiveProvider.
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
        # Fail closed — never construct SimulatedProvider in PRODUCTION
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
    if key in {"live", "bist", "broker", "http"}:
        url = os.getenv("MARKET_DATA_URL", "").strip()
        token = os.getenv("MARKET_DATA_TOKEN", "").strip()
        if not url or not token:
            return RequiredLiveProvider(
                "DATA_PROVIDER=live ancak MARKET_DATA_URL / MARKET_DATA_TOKEN yok"
            )
        return HttpLiveProviderStub(url, token)
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
        "Use simulated | required | live (needs MARKET_DATA_URL + MARKET_DATA_TOKEN)."
    )
