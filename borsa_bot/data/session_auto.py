"""Session-aware BIST provider — Yahoo when OPEN; Yahoo last/delayed when CLOSED.

Previously CLOSED switched to SimulatedProvider, which only covers a tiny
universe (~10 names) so BIST100 grids showed prices on a few tiles and dashes
on the rest. Off-hours we keep Yahoo last quotes and label them as closed.
"""

from __future__ import annotations

from typing import Any

from config.models import Bar, QuoteSnapshot
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, bist_session_now
from data.providers import SimulatedProvider
from data.yahoo_bist import YahooBistMarketDataProvider


class SessionAutoBistProvider:
    """DATA_PROVIDER=auto: Yahoo BIST always for quotes; sim only as last-resort fallback."""

    provider_id = "session_auto"
    display_name = "BIST auto (Yahoo · kapalıda son kapanış)"
    is_stub = False
    is_real_provider = True

    def __init__(self) -> None:
        self._yahoo = YahooBistMarketDataProvider()
        self._sim = SimulatedProvider()
        self._mode = "yahoo"  # yahoo | yahoo_closed | sim
        self._session = MarketSession.CLOSED

    def _active(self) -> Any:
        return self._yahoo if self._mode.startswith("yahoo") else self._sim

    @property
    def kind(self) -> DataSourceKind:
        return self._active().kind

    def tick(self) -> None:
        self._session = bist_session_now()
        if self._session == MarketSession.OPEN:
            self._mode = "yahoo"
            self._yahoo.tick(allow_closed=False)
            return
        # CLOSED: prefer Yahoo last/delayed board so all XU100 names can show a price.
        self._mode = "yahoo_closed"
        try:
            self._yahoo.tick(allow_closed=True)
            if self._yahoo.has_market_data():
                return
        except Exception:  # noqa: BLE001
            pass
        # Last resort — tiny sim universe (better than total blank if Yahoo is down)
        self._mode = "sim"
        self._sim.tick()

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        try:
            return self._yahoo.get_quote(symbol, allow_closed=True)
        except Exception:
            if self._mode == "sim":
                return self._sim.get_quote(symbol)
            raise

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        try:
            return self._yahoo.get_bars(symbol, lookback)
        except Exception:
            if self._mode == "sim":
                return self._sim.get_bars(symbol, lookback)
            raise

    def list_symbols(self) -> list[str]:
        return self._yahoo.list_symbols()

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        # Off-hours last quotes are intentionally older — use yahoo freshness gate
        return self._yahoo.is_fresh(max_age_sec)

    def has_market_data(self) -> bool:
        if self._mode.startswith("yahoo"):
            return self._yahoo.has_market_data()
        return self._sim.has_market_data()

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        if self._mode == "yahoo":
            return self._yahoo.source_meta(max_age_sec)
        if self._mode == "yahoo_closed":
            meta = self._yahoo.source_meta(max_age_sec)
            return DataSourceMeta(
                provider_id=self.provider_id,
                kind=meta.kind,
                display_name=self.display_name,
                connected=meta.connected,
                last_update=meta.last_update,
                age_seconds=meta.age_seconds,
                freshness=meta.freshness,
                market_session=MarketSession.CLOSED,
                is_live_market=False,
                live_ready=False,
                note="PİYASA KAPALI · son kapanış / gecikmeli Yahoo · canlı kotasyon değil",
                price_label="SON KAPANIŞ",
            )
        meta = self._sim.source_meta(max_age_sec)
        return DataSourceMeta(
            provider_id=self.provider_id,
            kind=meta.kind,
            display_name=self.display_name,
            connected=meta.connected,
            last_update=meta.last_update,
            age_seconds=meta.age_seconds,
            freshness=meta.freshness,
            market_session=MarketSession.CLOSED,
            is_live_market=False,
            live_ready=False,
            note=f"BIST CLOSED — Yahoo yok, simüle yedek. {meta.note}",
            price_label=meta.price_label,
        )

    def period_returns(self, symbol: str) -> dict:
        try:
            return self._yahoo.period_returns(symbol)
        except Exception:  # noqa: BLE001
            return {"daily_pct": None, "monthly_pct": None, "yearly_pct": None}
