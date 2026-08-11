"""Paribu live market-data provider — official api.paribu.com + public WS.

Implements MarketDataProvider contract. No trading / orders / API signing.
OHLCV: aggregated from public trades (official API has no candle endpoint).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from config.models import Bar, QuoteSnapshot
from crypto.http_client import DEFAULT_API_BASE, ParibuHTTPClient, ParibuHTTPError, ParibuRateLimitError
from crypto.market import MarketType
from crypto.ohlcv import TradeBarAccumulator
from crypto.rest import RawTrade, fetch_orderbook, fetch_recent_trades, fetch_tickers
from crypto.safety import crypto_provenance_fields
from crypto.symbols import CryptoSymbolMapper, normalize_crypto_app_symbol, to_display_symbol, to_paribu_market
from crypto.websocket import ParibuPublicStream
from data.contract import EnvironmentOrigin, stamp_bar_defaults, stamp_quote_defaults
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, build_source_meta

log = logging.getLogger("borsa_bot.crypto.paribu")


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
        return crypto_provenance_fields(provider_id=self.provider_id, data_source_kind=self.kind)


class ParibuMarketDataProvider:
    """LIVE Paribu adapter (public market data only).

    Classification: REAL when connected with ticker payload; never MOCK prices.
    """

    provider_id = "paribu"
    display_name = "Paribu (LIVE public market data)"
    is_stub = False
    is_real_provider = True
    market_type = MarketType.CRYPTO

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_API_BASE,
        api_key: str = "",
        api_secret: str = "",
        mapper: CryptoSymbolMapper | None = None,
        http: ParibuHTTPClient | None = None,
        enable_websocket: bool = True,
        poll_interval_sec: float = 3.0,
        ws_seed_markets: int = 8,
    ) -> None:
        del api_key, api_secret  # public MD only — keys unused (no trading)
        base = (api_base or DEFAULT_API_BASE).rstrip("/") or DEFAULT_API_BASE
        self.api_base = base
        self.http = http or ParibuHTTPClient(api_base=base, min_interval_sec=0.2)
        self.mapper = mapper or CryptoSymbolMapper(provider_id=self.provider_id)
        self.poll_interval_sec = max(1.0, float(poll_interval_sec))
        self.enable_websocket = enable_websocket
        self.ws_seed_markets = max(0, int(ws_seed_markets))
        self.kind = DataSourceKind.LIVE

        self._lock = threading.RLock()
        self._tickers: dict[str, Any] = {}  # provider market -> RawTicker
        self._quotes: dict[str, QuoteSnapshot] = {}  # app symbol
        self._last_tick: datetime | None = None
        self._connected = False
        self._error = ""
        self._accumulator = TradeBarAccumulator()
        self._stream: ParibuPublicStream | None = None
        self._ws_started = False

    # --- MarketDataProvider ---

    def tick(self) -> None:
        try:
            self._refresh_tickers()
            self._ensure_ws()
            self._error = ""
        except ParibuRateLimitError as exc:
            self._connected = False
            self._error = f"RATE_LIMIT:{exc.retry_after}"
            log.warning("paribu rate limit: %s", exc)
        except ParibuHTTPError as exc:
            self._connected = False
            self._error = f"HTTP_ERROR:{exc}"
            log.warning("paribu http: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            self._error = f"PROVIDER_FAILURE:{exc}"
            log.exception("paribu tick failure")

    def list_symbols(self) -> list[str]:
        with self._lock:
            if not self._tickers:
                try:
                    self._refresh_tickers()
                except Exception:  # noqa: BLE001
                    return []
            return sorted({normalize_crypto_app_symbol(m) for m in self._tickers.keys()})

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        app = normalize_crypto_app_symbol(symbol)
        if not app:
            raise RuntimeError("NO_MARKET_DATA: empty symbol")
        try:
            self._hydrate_quote(app)
        except Exception:
            # fall back to ticker-only cache
            if not self._connected:
                self.tick()
            with self._lock:
                q = self._quotes.get(app)
            if q is None:
                raise RuntimeError(f"NO_MARKET_DATA: {app}")
            return q
        with self._lock:
            q = self._quotes.get(app)
        if q is None:
            raise RuntimeError(f"NO_MARKET_DATA: {app}")
        return q

    def ticker_stats(self, symbol: str) -> dict[str, Any]:
        """24h change / volume from Paribu ticker cache (percentage field)."""
        app = normalize_crypto_app_symbol(symbol)
        market = to_paribu_market(app)
        with self._lock:
            raw = self._tickers.get(market)
        if raw is None:
            return {}
        return {
            "change_pct": float(raw.percentage),
            "change": float(raw.change),
            "volume": float(raw.volume),
            "high": float(raw.high),
            "low": float(raw.low),
            "first": float(raw.first),
        }

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        app = normalize_crypto_app_symbol(symbol)
        self._ingest_rest_trades(app)
        bars = self._accumulator.bars(app, timeframe="15m", lookback=lookback)
        return bars

    def get_bars_tf(self, symbol: str, timeframe: str, lookback: int = 220) -> list[Bar]:
        app = normalize_crypto_app_symbol(symbol)
        self._ingest_rest_trades(app)
        return self._accumulator.bars(app, timeframe=timeframe, lookback=lookback)

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        if not self._last_tick:
            return False
        age = (datetime.now(timezone.utc) - self._last_tick).total_seconds()
        return age <= max_age_sec and self._connected

    def has_market_data(self) -> bool:
        with self._lock:
            return self._connected and bool(self._tickers)

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        note = self._error or ("Paribu LIVE public ticker/orderbook" if self._connected else "disconnected")
        return build_source_meta(
            provider_id=self.provider_id,
            kind=DataSourceKind.LIVE if self._connected else DataSourceKind.UNAVAILABLE,
            display_name=self.display_name,
            connected=self._connected,
            last_update=self._last_tick,
            max_age_sec=max_age_sec,
            live_ready=False,  # trading/broker not enabled
            note=note,
        )

    def provenance(self) -> dict[str, str]:
        kind = DataSourceKind.LIVE if self._connected else DataSourceKind.UNAVAILABLE
        return crypto_provenance_fields(provider_id=self.provider_id, data_source_kind=kind)

    def status_dict(self) -> dict:
        meta = self.source_meta()
        d = meta.to_dict()
        d.update(self.provenance())
        d["stub"] = False
        d["real_provider"] = True
        d["http_connected"] = self._connected
        d["websocket"] = {
            "enabled": self.enable_websocket,
            "connected": bool(self._stream and self._stream.state.connected),
            "reconnects": self._stream.state.reconnects if self._stream else 0,
            "last_error": self._stream.state.last_error if self._stream else "",
        }
        d["symbols"] = len(self.list_symbols())
        d["ohlcv_note"] = "aggregated from public trades; no official candle endpoint"
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        return d

    def close(self) -> None:
        if self._stream:
            self._stream.stop()

    # --- internals ---

    def _refresh_tickers(self) -> None:
        rows = fetch_tickers(self.http, cache_ttl_sec=self.poll_interval_sec)
        if not rows:
            raise ParibuHTTPError("empty ticker list")
        now = datetime.now(timezone.utc)
        with self._lock:
            self._tickers = {r.market: r for r in rows if r.market}
            for market, raw in self._tickers.items():
                app = normalize_crypto_app_symbol(market)
                self.mapper.register(app, market)
                # lightweight quote from ticker; bid/ask filled lazily / via WS
                existing = self._quotes.get(app)
                bid = existing.bid if existing and existing.bid > 0 else raw.last
                ask = existing.ask if existing and existing.ask > 0 else raw.last
                if bid <= 0 or ask <= 0:
                    continue
                if ask < bid:
                    bid, ask = ask, bid
                q = QuoteSnapshot(
                    symbol=app,
                    name=to_display_symbol(app),
                    sector="CRYPTO",
                    price=float(raw.last),
                    bid=float(bid),
                    ask=float(ask),
                    volume=float(raw.volume),
                    trades=0,
                    ts=now,
                    data_source_kind=DataSourceKind.LIVE.value,
                    provider=self.provider_id,
                    environment_origin=EnvironmentOrigin.LIVE.value,
                    market_status=MarketSession.OPEN.value,
                    received_at=now,
                )
                # Avoid BIST session overwrite
                stamp_quote_defaults(q, provider=self.provider_id, origin=EnvironmentOrigin.LIVE)
                q.symbol = app
                q.market_status = MarketSession.OPEN.value
                self._quotes[app] = q
            self._connected = True
            self._last_tick = now
            self.kind = DataSourceKind.LIVE

    def _hydrate_quote(self, app_symbol: str) -> None:
        market = to_paribu_market(app_symbol)
        rows = fetch_tickers(self.http, market=market, cache_ttl_sec=0)
        if not rows:
            raise RuntimeError("ticker empty")
        raw = rows[0]
        book = fetch_orderbook(self.http, market, depth=5, cache_ttl_sec=0)
        now = datetime.now(timezone.utc)
        ts = book.timestamp if book.timestamp.tzinfo else now
        q = QuoteSnapshot(
            symbol=app_symbol,
            name=to_display_symbol(app_symbol),
            sector="CRYPTO",
            price=float(raw.last),
            bid=float(book.bid),
            ask=float(book.ask),
            volume=float(raw.volume),
            trades=0,
            ts=ts,
            data_source_kind=DataSourceKind.LIVE.value,
            provider=self.provider_id,
            environment_origin=EnvironmentOrigin.LIVE.value,
            market_status=MarketSession.OPEN.value,
            received_at=now,
        )
        stamp_quote_defaults(q, provider=self.provider_id, origin=EnvironmentOrigin.LIVE)
        q.symbol = app_symbol
        q.market_status = MarketSession.OPEN.value
        with self._lock:
            self._quotes[app_symbol] = q
            self._tickers[market] = raw
            self.mapper.register(app_symbol, market)
            self._connected = True
            self._last_tick = now

    def _ingest_rest_trades(self, app_symbol: str) -> None:
        market = to_paribu_market(app_symbol)
        try:
            trades = fetch_recent_trades(self.http, market, limit=5, cache_ttl_sec=2.0)
        except Exception as exc:  # noqa: BLE001
            log.debug("trades fetch failed %s: %s", market, exc)
            return
        self._accumulator.add_trades(app_symbol, trades)

    def _ensure_ws(self) -> None:
        if not self.enable_websocket or self._ws_started:
            return
        markets = sorted(self._tickers.keys())[: self.ws_seed_markets]
        if not markets:
            return
        channels: list[str] = []
        for m in markets:
            channels.extend([f"match-price:{m}", f"matches:{m}", f"orderbook:{m}"])

        def on_match_price(market: str, price: float, ts: datetime) -> None:
            app = normalize_crypto_app_symbol(market)
            with self._lock:
                q = self._quotes.get(app)
                if q is None:
                    return
                q.price = price
                q.ts = ts
                q.received_at = datetime.now(timezone.utc)
                self._last_tick = q.received_at

        def on_match(market: str, price: float, qty: float, ts: datetime) -> None:
            app = normalize_crypto_app_symbol(market)
            self._accumulator.add_trade(app, RawTrade(price=price, amount=qty, time=ts, side=""))
            on_match_price(market, price, ts)

        def on_book(market: str, bid: float, ask: float, ts: datetime) -> None:
            app = normalize_crypto_app_symbol(market)
            with self._lock:
                q = self._quotes.get(app)
                if q is None:
                    return
                if bid > 0 and ask > 0 and ask >= bid:
                    q.bid = bid
                    q.ask = ask
                    q.ts = ts
                    q.received_at = datetime.now(timezone.utc)
                    self._last_tick = q.received_at

        self._stream = ParibuPublicStream(
            on_match_price=on_match_price,
            on_match=on_match,
            on_book_top=on_book,
        )
        self._stream.set_channels(channels)
        self._stream.start()
        self._ws_started = True
