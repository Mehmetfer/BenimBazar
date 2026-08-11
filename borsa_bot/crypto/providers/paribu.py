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
from crypto.markets import CryptoMarketInfo, build_market_catalog
from crypto.ohlcv import TradeBarAccumulator
from crypto.rest import RawTrade, fetch_orderbook, fetch_recent_trades, fetch_tickers
from crypto.safety import crypto_provenance_fields
from crypto.symbols import CryptoSymbolMapper, normalize_crypto_app_symbol, to_display_symbol, to_paribu_market
from crypto.trade_store import CryptoTradeStore
from crypto.websocket import ParibuPublicStream
from data.contract import EnvironmentOrigin, compute_spread_pct, stamp_quote_defaults
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, build_source_meta
from dataclasses import replace

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

    def health_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "connected": False,
            "market_count": 0,
            "valid_symbols": 0,
            "rejected_symbols": 0,
            "last_update": None,
            "data_fresh": False,
            "ohlcv_ready": False,
            "websocket": {"enabled": False, "connected": False, "state": "DISABLED"},
            "rest": False,
            "errors": [self.reason],
            "note": "CRYPTO plane off or misconfigured — NO MOCK FALLBACK",
            "live_trading": False,
        }


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
        trade_store: CryptoTradeStore | None = None,
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
        self._markets: dict[str, CryptoMarketInfo] = {}
        self._last_tick: datetime | None = None
        self._connected = False
        self._error = ""
        self._api_errors = 0
        self._rejected_symbols = 0
        self._accumulator = TradeBarAccumulator()
        self._trade_store = trade_store if trade_store is not None else CryptoTradeStore()
        self._stream: ParibuPublicStream | None = None
        self._ws_started = False
        self._bid_ask_known: dict[str, bool] = {}

    # --- MarketDataProvider ---

    def tick(self) -> None:
        try:
            self._refresh_tickers()
            self._ensure_ws()
            self._error = ""
        except ParibuRateLimitError as exc:
            self._connected = False
            self._error = f"RATE_LIMIT:{exc.retry_after}"
            self._api_errors += 1
            log.warning("paribu rate limit: %s", exc)
        except ParibuHTTPError as exc:
            self._connected = False
            self._error = f"HTTP_ERROR:{exc}"
            self._api_errors += 1
            log.warning("paribu http: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            self._error = f"PROVIDER_FAILURE:{exc}"
            self._api_errors += 1
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
        # Prefer persisted + in-memory merge (never invent history)
        stored = self._trade_store.bars(app, timeframe="15m", lookback=lookback, provider=self.provider_id)
        live = self._accumulator.bars(app, timeframe="15m", lookback=lookback)
        return self._merge_bars(stored, live, lookback=lookback)

    def get_bars_tf(self, symbol: str, timeframe: str, lookback: int = 220) -> list[Bar]:
        app = normalize_crypto_app_symbol(symbol)
        self._ingest_rest_trades(app)
        stored = self._trade_store.bars(app, timeframe=timeframe, lookback=lookback, provider=self.provider_id)
        live = self._accumulator.bars(app, timeframe=timeframe, lookback=lookback)
        return self._merge_bars(stored, live, lookback=lookback)

    def list_markets(self) -> list[CryptoMarketInfo]:
        with self._lock:
            if not self._markets:
                try:
                    self._refresh_tickers()
                except Exception:  # noqa: BLE001
                    return []
            return list(self._markets.values())

    def bid_ask_known(self, symbol: str) -> bool:
        app = normalize_crypto_app_symbol(symbol)
        with self._lock:
            return bool(self._bid_ask_known.get(app))

    def quote_spread_pct(self, quote: QuoteSnapshot) -> float | None:
        """None when bid/ask unknown — never invent spread from last."""
        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            return None
        return compute_spread_pct(quote.bid, quote.ask)

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
        meta = build_source_meta(
            provider_id=self.provider_id,
            kind=DataSourceKind.LIVE if self._connected else DataSourceKind.UNAVAILABLE,
            display_name=self.display_name,
            connected=self._connected,
            last_update=self._last_tick,
            max_age_sec=max_age_sec,
            live_ready=False,  # trading/broker not enabled
            note=note,
        )
        # Crypto is 24/7 — do not inherit BIST session CLOSED from build_source_meta
        session = MarketSession.OPEN if self._connected else MarketSession.UNKNOWN
        if self._error.startswith("HTTP_ERROR") or self._error.startswith("PROVIDER_FAILURE"):
            session = MarketSession.UNKNOWN
            note = f"MARKET_UNAVAILABLE:{self._error}"
        return replace(meta, market_session=session, note=note or meta.note)

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
        d["markets_discovered"] = len(self._markets)
        d["ohlcv_note"] = (
            "aggregated from public trades (/trades limit<=20) + WS matches; "
            "no official candle endpoint — 240×15m requires accumulated history"
        )
        d["trade_store"] = self._trade_store.stats()
        d["api_errors"] = self._api_errors
        d["rejected_symbols"] = self._rejected_symbols
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        return d

    def health_dict(self) -> dict[str, Any]:
        """Debug/ops snapshot for GET /api/crypto/health."""
        try:
            if not self._connected:
                self.tick()
        except Exception:  # noqa: BLE001
            pass
        meta = self.source_meta()
        bars_ready = 0
        sample_sym = None
        with self._lock:
            symbols = sorted(self._quotes.keys())
        if symbols:
            sample_sym = "BTC_TL" if "BTC_TL" in symbols else symbols[0]
            bars_ready = len(self.get_bars(sample_sym, lookback=240))
        return {
            "provider": self.provider_id,
            "connected": self._connected,
            "market_count": len(self.list_symbols()),
            "valid_symbols": len([m for m in self.list_markets() if m.status == "ACTIVE"]),
            "rejected_symbols": self._rejected_symbols,
            "last_update": meta.last_update,
            "data_fresh": self.is_fresh(),
            "freshness": meta.freshness.value if hasattr(meta.freshness, "value") else str(meta.freshness),
            "ohlcv_ready": bars_ready >= 240,
            "ohlcv_bars_sample": bars_ready,
            "ohlcv_sample_symbol": sample_sym,
            "websocket": {
                "enabled": self.enable_websocket,
                "connected": bool(self._stream and self._stream.state.connected),
                "state": (
                    "CONNECTED"
                    if (self._stream and self._stream.state.connected)
                    else ("DISABLED" if not self.enable_websocket else "DISCONNECTED")
                ),
                "reconnects": self._stream.state.reconnects if self._stream else 0,
            },
            "rest": True,
            "errors": [self._error] if self._error else [],
            "api_errors": self._api_errors,
            "trade_store": self._trade_store.stats(),
            "market_session": meta.market_session.value,
            "source_kind": meta.kind.value if hasattr(meta.kind, "value") else str(meta.kind),
            "live_trading": False,
            "note": "REAL MD + PAPER only this phase — no live crypto orders",
        }

    def close(self) -> None:
        if self._stream:
            self._stream.stop()

    # --- internals ---

    @staticmethod
    def _merge_bars(a: list[Bar], b: list[Bar], *, lookback: int) -> list[Bar]:
        by_ts: dict[datetime, Bar] = {}
        for bar in a + b:
            by_ts[bar.ts] = bar
        return [by_ts[k] for k in sorted(by_ts.keys())][-lookback:]

    def _refresh_tickers(self) -> None:
        rows = fetch_tickers(self.http, cache_ttl_sec=self.poll_interval_sec)
        if not rows:
            raise ParibuHTTPError("empty ticker list")
        catalog = build_market_catalog(rows)
        now = datetime.now(timezone.utc)
        rejected = 0
        with self._lock:
            self._tickers = {r.market: r for r in rows if r.market}
            self._markets = {m.canonical_symbol: m for m in catalog}
            for market, raw in self._tickers.items():
                app = normalize_crypto_app_symbol(market)
                if not app or raw.last <= 0:
                    rejected += 1
                    continue
                self.mapper.register(app, market)
                existing = self._quotes.get(app)
                known = bool(self._bid_ask_known.get(app))
                # NEVER invent bid/ask = last (§17). Keep unknown until orderbook/WS.
                if known and existing and existing.bid > 0 and existing.ask > 0:
                    bid, ask = float(existing.bid), float(existing.ask)
                else:
                    bid, ask = 0.0, 0.0
                    self._bid_ask_known[app] = False
                q = QuoteSnapshot(
                    symbol=app,
                    name=to_display_symbol(app),
                    sector="CRYPTO",
                    price=float(raw.last),
                    bid=bid,
                    ask=ask,
                    volume=float(raw.volume),
                    trades=0,
                    ts=now,
                    data_source_kind=DataSourceKind.LIVE.value,
                    provider=self.provider_id,
                    environment_origin=EnvironmentOrigin.LIVE.value,
                    market_status=MarketSession.OPEN.value,
                    received_at=now,
                )
                stamp_quote_defaults(q, provider=self.provider_id, origin=EnvironmentOrigin.LIVE)
                q.symbol = app
                q.market_status = MarketSession.OPEN.value
                self._quotes[app] = q
            self._rejected_symbols = rejected
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
        if book.bid <= 0 or book.ask <= 0 or book.ask < book.bid:
            raise RuntimeError("INVALID_ORDERBOOK")
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
            self._bid_ask_known[app_symbol] = True
            self._connected = True
            self._last_tick = now

    def _ingest_rest_trades(self, app_symbol: str) -> None:
        market = to_paribu_market(app_symbol)
        try:
            trades = fetch_recent_trades(self.http, market, limit=20, cache_ttl_sec=2.0)
        except Exception as exc:  # noqa: BLE001
            log.debug("trades fetch failed %s: %s", market, exc)
            return
        self._accumulator.add_trades(app_symbol, trades)
        self._trade_store.add_trades(app_symbol, trades, provider_symbol=market, provider=self.provider_id)

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
            trade = RawTrade(price=price, amount=qty, time=ts, side="")
            self._accumulator.add_trade(app, trade)
            self._trade_store.add_trades(app, [trade], provider_symbol=market, provider=self.provider_id)
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
                    self._bid_ask_known[app] = True
                    self._last_tick = q.received_at

        self._stream = ParibuPublicStream(
            on_match_price=on_match_price,
            on_match=on_match,
            on_book_top=on_book,
        )
        self._stream.set_channels(channels)
        self._stream.start()
        self._ws_started = True
