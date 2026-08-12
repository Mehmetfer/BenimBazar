"""Session-aware BIST provider — Yahoo when market OPEN, simulated when CLOSED."""

from __future__ import annotations

from typing import Any

from config.models import Bar, QuoteSnapshot
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, bist_session_now
from data.providers import SimulatedProvider
from data.yahoo_bist import YahooBistMarketDataProvider


class SessionAutoBistProvider:
    """DATA_PROVIDER=auto: real Yahoo BIST during session; paper sim off-hours."""

    provider_id = "session_auto"
    display_name = "BIST auto (Yahoo OPEN · simulated CLOSED)"
    is_stub = False
    is_real_provider = True

    def __init__(self) -> None:
        self._yahoo = YahooBistMarketDataProvider()
        self._sim = SimulatedProvider()
        self._mode = "sim"

    def _active(self) -> Any:
        return self._yahoo if self._mode == "yahoo" else self._sim

    @property
    def kind(self) -> DataSourceKind:
        return self._active().kind

    def tick(self) -> None:
        session = bist_session_now()
        self._mode = "yahoo" if session == MarketSession.OPEN else "sim"
        self._active().tick()

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return self._active().get_quote(symbol)

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return self._active().get_bars(symbol, lookback)

    def list_symbols(self) -> list[str]:
        return self._active().list_symbols()

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return self._active().is_fresh(max_age_sec)

    def has_market_data(self) -> bool:
        return self._active().has_market_data()

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        meta = self._active().source_meta(max_age_sec)
        if self._mode == "yahoo":
            return meta
        # Annotate off-hours simulated fallback
        return DataSourceMeta(
            provider_id=self.provider_id,
            kind=meta.kind,
            display_name=self.display_name,
            connected=meta.connected,
            last_update=meta.last_update,
            age_seconds=meta.age_seconds,
            freshness=meta.freshness,
            market_session=meta.market_session,
            is_live_market=False,
            live_ready=False,
            note=f"BIST CLOSED — simulated paper feed. {meta.note}",
            price_label=meta.price_label,
        )
