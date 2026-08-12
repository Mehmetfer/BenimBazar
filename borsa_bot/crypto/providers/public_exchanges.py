"""Public crypto market-data providers — same sources open-source bots use (CCXT-style).

GitHub trading stacks (ccxt, freqtrade, etc.) pull free public REST from
OKX / Gate / Kraken / Coinbase. We mirror that approach without inventing prices.

No API keys. No orders. market_type=CRYPTO only. BIST untouched.
Binance may be geo-blocked (HTTP 451) — failover skips unreachable venues.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config.models import Bar, QuoteSnapshot
from crypto.market import MarketType
from crypto.markets import CryptoMarketInfo
from crypto.safety import crypto_provenance_fields
from crypto.symbols import normalize_crypto_app_symbol, to_display_symbol
from data.contract import EnvironmentOrigin, compute_spread_pct, stamp_bar_defaults, stamp_quote_defaults
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, build_source_meta

log = logging.getLogger("borsa_bot.crypto.public")

_UA = "borsa-bot/crypto-public-md (+https://github.com/ccxt/ccxt-style-public-md)"


def _http_json(url: str, *, timeout: float = 12.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public MD URLs from code
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def _ms_to_dt(ms: int | float | str) -> datetime:
    v = float(ms)
    if v > 1e12:  # ms
        v = v / 1000.0
    return datetime.fromtimestamp(v, tz=timezone.utc)


class _PublicExchangeBase:
    """Shared MarketDataProvider surface for public CEX REST."""

    market_type = MarketType.CRYPTO
    is_stub = False
    is_real_provider = True
    kind = DataSourceKind.LIVE

    def __init__(self) -> None:
        self._connected = False
        self._last_ok: datetime | None = None
        self._error = ""
        self._symbols: list[str] = []
        self._native: dict[str, str] = {}  # app_symbol → exchange id
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._tickers: dict[str, dict[str, Any]] = {}

    def tick(self) -> None:
        try:
            self._refresh_markets()
            self._refresh_tickers()
            self._connected = bool(self._tickers)
            self._last_ok = datetime.now(timezone.utc)
            self._error = "" if self._connected else "NO_TICKERS"
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            self._error = str(exc)
            log.warning("%s tick failed: %s", self.provider_id, type(exc).__name__)

    def list_symbols(self) -> list[str]:
        return list(self._symbols)

    def list_markets(self) -> list[CryptoMarketInfo]:
        out: list[CryptoMarketInfo] = []
        for app in self._symbols:
            base, _, quote = app.partition("_")
            out.append(
                CryptoMarketInfo(
                    canonical_symbol=app,
                    provider_symbol=self._native.get(app, app),
                    display=to_display_symbol(app),
                    base_asset=base,
                    quote_asset=quote,
                    market_id=self._native.get(app, app),
                    status="ACTIVE",
                    provider=self.provider_id,
                    market_type="CRYPTO",
                )
            )
        return out

    def has_market_data(self) -> bool:
        return self._connected and bool(self._tickers)

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        if not self._last_ok or not self._connected:
            return False
        return (datetime.now(timezone.utc) - self._last_ok).total_seconds() <= max_age_sec

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self.kind if self._connected else DataSourceKind.UNAVAILABLE,
            display_name=self.display_name,
            connected=self._connected,
            last_update=self._last_ok,
            max_age_sec=max_age_sec,
            live_ready=self._connected,
            note=self._error or f"CRYPTO · {self.provider_id} public REST · session OPEN 24/7",
        )

    def provenance(self) -> dict[str, str]:
        kind = self.kind if self._connected else DataSourceKind.UNAVAILABLE
        return crypto_provenance_fields(provider_id=self.provider_id, data_source_kind=kind)

    def health_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "connected": self._connected,
            "market_count": len(self._symbols),
            "valid_symbols": len(self._symbols),
            "rejected_symbols": 0,
            "last_update": self._last_ok.isoformat() if self._last_ok else None,
            "data_fresh": self.is_fresh(),
            "ohlcv_ready": True,
            "websocket": {"enabled": False, "connected": False, "state": "REST_ONLY"},
            "rest": self._connected,
            "errors": [self._error] if self._error else [],
            "note": "Public CEX REST (ccxt-style sources) — no mock fallback",
            "live_trading": False,
            "exchange": getattr(self, "exchange_id", self.provider_id),
        }

    def ticker_stats(self, symbol: str) -> dict[str, Any]:
        app = normalize_crypto_app_symbol(symbol)
        t = self._tickers.get(app) or {}
        return {
            "symbol": app,
            "last": t.get("last"),
            "bid": t.get("bid"),
            "ask": t.get("ask"),
            "volume": t.get("volume"),
            "high": t.get("high"),
            "low": t.get("low"),
            "provider": self.provider_id,
        }

    def bid_ask_known(self, symbol: str) -> bool:
        app = normalize_crypto_app_symbol(symbol)
        t = self._tickers.get(app) or {}
        return t.get("bid") is not None and t.get("ask") is not None

    def quote_spread_pct(self, quote: QuoteSnapshot) -> float | None:
        """None when bid/ask unknown — never invent spread from last."""
        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            return None
        return compute_spread_pct(float(quote.bid), float(quote.ask))

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        app = normalize_crypto_app_symbol(symbol)
        if not self._tickers:
            self.tick()
        t = self._tickers.get(app)
        if not t or t.get("last") is None:
            raise RuntimeError(f"NO_MARKET_DATA: {self.provider_id} has no ticker for {app}")
        last = float(t["last"])
        bid = float(t["bid"]) if t.get("bid") is not None else None
        ask = float(t["ask"]) if t.get("ask") is not None else None
        # Never invent bid/ask from last (same honesty rule as Paribu)
        known = bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid
        q = QuoteSnapshot(
            symbol=app,
            name=to_display_symbol(app),
            sector="CRYPTO",
            price=last,
            bid=float(bid) if known else 0.0,
            ask=float(ask) if known else 0.0,
            volume=float(t.get("volume") or 0),
            trades=int(t.get("trades") or 0),
            ts=_ms_to_dt(t["ts"]) if t.get("ts") else datetime.now(timezone.utc),
            data_source_kind=DataSourceKind.LIVE.value,
            provider=self.provider_id,
            environment_origin=EnvironmentOrigin.LIVE.value,
            market_status=MarketSession.OPEN.value,
            received_at=datetime.now(timezone.utc),
        )
        q = stamp_quote_defaults(q, provider=self.provider_id, origin=EnvironmentOrigin.LIVE)
        # Keep crypto OPEN — stamp helpers default to BIST session otherwise
        q.market_status = MarketSession.OPEN.value
        self._quotes[app] = q
        return q

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return self.get_bars_tf(symbol, "15m", lookback=lookback)

    def get_bars_tf(self, symbol: str, timeframe: str, lookback: int = 220) -> list[Bar]:
        app = normalize_crypto_app_symbol(symbol)
        native = self._native.get(app)
        if not native:
            if not self._symbols:
                self.tick()
            native = self._native.get(app)
        if not native:
            raise RuntimeError(f"NO_MARKET_DATA: unknown symbol {app} on {self.provider_id}")
        bars = self._fetch_ohlcv(native, timeframe, lookback)
        if not bars:
            raise RuntimeError(f"NO_MARKET_DATA: empty OHLCV {app}@{timeframe} from {self.provider_id}")
        return bars

    def close(self) -> None:
        return None

    # --- subclass hooks ---
    def _refresh_markets(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _refresh_tickers(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _fetch_ohlcv(self, native_id: str, timeframe: str, lookback: int) -> list[Bar]:  # pragma: no cover
        raise NotImplementedError


class OkxPublicProvider(_PublicExchangeBase):
    """OKX public REST — widely used via CCXT (`okx`)."""

    provider_id = "okx_public"
    display_name = "OKX Public Market Data"
    exchange_id = "okx"
    _BASE = "https://www.okx.com"

    _TF = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
        "1w": "1W",
    }

    def _app_from_inst(self, inst_id: str) -> str:
        # BTC-USDT → BTC_USDT
        return normalize_crypto_app_symbol(inst_id.replace("-", "_"))

    def _refresh_markets(self) -> None:
        data = _http_json(f"{self._BASE}/api/v5/public/instruments?instType=SPOT")
        rows = data.get("data") if isinstance(data, dict) else []
        symbols: list[str] = []
        native: dict[str, str] = {}
        for row in rows or []:
            if str(row.get("state") or "").lower() not in {"live", ""}:
                # OKX uses state=live
                if str(row.get("state") or "") != "live":
                    continue
            inst = str(row.get("instId") or "")
            quote = str(row.get("quoteCcy") or "").upper()
            if quote not in {"USDT", "USD", "USDC"}:
                continue
            app = self._app_from_inst(inst)
            if not app:
                continue
            symbols.append(app)
            native[app] = inst
        self._symbols = sorted(set(symbols))
        self._native = native

    def _refresh_tickers(self) -> None:
        data = _http_json(f"{self._BASE}/api/v5/market/tickers?instType=SPOT")
        rows = data.get("data") if isinstance(data, dict) else []
        tickers: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            inst = str(row.get("instId") or "")
            app = self._app_from_inst(inst)
            if app not in self._native and self._native:
                continue
            if not app:
                continue
            try:
                last = float(row["last"]) if row.get("last") not in (None, "") else None
            except (TypeError, ValueError, KeyError):
                continue
            if last is None:
                continue
            bid = ask = None
            try:
                if row.get("bidPx") not in (None, ""):
                    bid = float(row["bidPx"])
                if row.get("askPx") not in (None, ""):
                    ask = float(row["askPx"])
            except (TypeError, ValueError):
                bid = ask = None
            ts = row.get("ts")
            tickers[app] = {
                "last": last,
                "bid": bid,
                "ask": ask,
                "volume": float(row.get("vol24h") or 0),
                "high": float(row["high24h"]) if row.get("high24h") not in (None, "") else None,
                "low": float(row["low24h"]) if row.get("low24h") not in (None, "") else None,
                "ts": int(ts) if ts else None,
            }
            if app not in self._native:
                self._native[app] = inst
        if tickers and not self._symbols:
            self._symbols = sorted(tickers.keys())
        self._tickers = tickers

    def _fetch_ohlcv(self, native_id: str, timeframe: str, lookback: int) -> list[Bar]:
        bar = self._TF.get(timeframe.lower(), "15m")
        limit = min(max(lookback, 1), 300)
        url = (
            f"{self._BASE}/api/v5/market/candles?instId={urllib.parse.quote(native_id)}"
            f"&bar={urllib.parse.quote(bar)}&limit={limit}"
        )
        data = _http_json(url)
        rows = data.get("data") if isinstance(data, dict) else []
        app = self._app_from_inst(native_id)
        out: list[Bar] = []
        # OKX returns newest first
        for row in reversed(rows or []):
            # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            try:
                ts = _ms_to_dt(row[0])
                o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                vol = float(row[5]) if len(row) > 5 else 0.0
            except (TypeError, ValueError, IndexError):
                continue
            out.append(
                stamp_bar_defaults(
                    Bar(
                        ts=ts,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=vol,
                        trades=0,
                        symbol=app,
                        timeframe=timeframe.lower(),
                        data_source_kind=DataSourceKind.LIVE.value,
                        provider=self.provider_id,
                        environment_origin=EnvironmentOrigin.LIVE.value,
                        received_at=datetime.now(timezone.utc),
                    ),
                    provider=self.provider_id,
                    origin=EnvironmentOrigin.LIVE,
                    timeframe=timeframe.lower(),
                )
            )
        return out[-lookback:]


class GatePublicProvider(_PublicExchangeBase):
    """Gate.io public REST — common CCXT `gate` source."""

    provider_id = "gate_public"
    display_name = "Gate.io Public Market Data"
    exchange_id = "gate"
    _BASE = "https://api.gateio.ws/api/v4"

    _TF = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1w": "7d",
    }

    def _refresh_markets(self) -> None:
        rows = _http_json(f"{self._BASE}/spot/currency_pairs")
        symbols: list[str] = []
        native: dict[str, str] = {}
        for row in rows or []:
            if str(row.get("trade_status") or "") not in {"tradable", ""}:
                if str(row.get("trade_status") or "") != "tradable":
                    continue
            pair = str(row.get("id") or "")
            quote = str(row.get("quote") or "").upper()
            if quote not in {"USDT", "USD", "USDC"}:
                continue
            app = normalize_crypto_app_symbol(pair)
            symbols.append(app)
            native[app] = pair
        self._symbols = sorted(set(symbols))
        self._native = native

    def _refresh_tickers(self) -> None:
        rows = _http_json(f"{self._BASE}/spot/tickers")
        tickers: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            pair = str(row.get("currency_pair") or "")
            app = normalize_crypto_app_symbol(pair)
            if self._native and app not in self._native:
                continue
            try:
                last = float(row["last"])
            except (TypeError, ValueError, KeyError):
                continue
            bid = ask = None
            try:
                if row.get("highest_bid") not in (None, ""):
                    bid = float(row["highest_bid"])
                if row.get("lowest_ask") not in (None, ""):
                    ask = float(row["lowest_ask"])
            except (TypeError, ValueError):
                pass
            tickers[app] = {
                "last": last,
                "bid": bid,
                "ask": ask,
                "volume": float(row.get("base_volume") or 0),
                "high": float(row["high_24h"]) if row.get("high_24h") not in (None, "") else None,
                "low": float(row["low_24h"]) if row.get("low_24h") not in (None, "") else None,
                "ts": None,
            }
            if app not in self._native:
                self._native[app] = pair
        if tickers and not self._symbols:
            self._symbols = sorted(tickers.keys())
        self._tickers = tickers

    def _fetch_ohlcv(self, native_id: str, timeframe: str, lookback: int) -> list[Bar]:
        interval = self._TF.get(timeframe.lower(), "15m")
        limit = min(max(lookback, 1), 1000)
        url = (
            f"{self._BASE}/spot/candlesticks?currency_pair={urllib.parse.quote(native_id)}"
            f"&interval={urllib.parse.quote(interval)}&limit={limit}"
        )
        rows = _http_json(url)
        app = normalize_crypto_app_symbol(native_id)
        out: list[Bar] = []
        # Gate: [t, vol_quote, close, high, low, open, base_vol, ...] oldest first or mixed
        for row in rows or []:
            try:
                ts = _ms_to_dt(int(row[0]))
                o, h, l, c = float(row[5]), float(row[3]), float(row[4]), float(row[2])
                vol = float(row[6]) if len(row) > 6 else float(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            out.append(
                stamp_bar_defaults(
                    Bar(
                        ts=ts,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=vol,
                        trades=0,
                        symbol=app,
                        timeframe=timeframe.lower(),
                        data_source_kind=DataSourceKind.LIVE.value,
                        provider=self.provider_id,
                        environment_origin=EnvironmentOrigin.LIVE.value,
                        received_at=datetime.now(timezone.utc),
                    ),
                    provider=self.provider_id,
                    origin=EnvironmentOrigin.LIVE,
                    timeframe=timeframe.lower(),
                )
            )
        out.sort(key=lambda b: b.ts)
        return out[-lookback:]


class KrakenPublicProvider(_PublicExchangeBase):
    """Kraken public REST — CCXT `kraken` public endpoints (USD pairs primary)."""

    provider_id = "kraken_public"
    display_name = "Kraken Public Market Data"
    exchange_id = "kraken"
    _BASE = "https://api.kraken.com/0/public"

    _TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}

    def _refresh_markets(self) -> None:
        data = _http_json(f"{self._BASE}/AssetPairs")
        result = (data or {}).get("result") or {}
        symbols: list[str] = []
        native: dict[str, str] = {}
        for pair_id, row in result.items():
            if not isinstance(row, dict):
                continue
            if row.get("wsname"):
                disp = str(row["wsname"])  # XBT/USD
            else:
                disp = str(pair_id)
            app = normalize_crypto_app_symbol(disp.replace("XBT", "BTC"))
            quote = app.split("_")[-1] if "_" in app else ""
            if quote not in {"USD", "USDT", "USDC", "EUR"}:
                continue
            # Prefer altname for OHLC
            alt = str(row.get("altname") or pair_id)
            symbols.append(app)
            native[app] = alt
        self._symbols = sorted(set(symbols))
        self._native = native

    def _refresh_tickers(self) -> None:
        if not self._native:
            self._refresh_markets()
        # Batch a subset to avoid huge URLs — top majors + all if small
        pairs = list(self._native.values())
        # Kraken allows comma-separated; cap to avoid URL limits
        chunk = pairs[:80]
        if not chunk:
            self._tickers = {}
            return
        q = urllib.parse.quote(",".join(chunk))
        data = _http_json(f"{self._BASE}/Ticker?pair={q}")
        result = (data or {}).get("result") or {}
        # Map reverse native→app
        rev = {v: k for k, v in self._native.items()}
        tickers: dict[str, dict[str, Any]] = {}
        for pair_id, row in result.items():
            app = rev.get(pair_id)
            if not app:
                # try match by suffix
                for alt, a in rev.items():
                    if pair_id.endswith(alt) or alt in pair_id:
                        app = a
                        break
            if not app or not isinstance(row, dict):
                continue
            try:
                last = float(row["c"][0])
                bid = float(row["b"][0]) if row.get("b") else None
                ask = float(row["a"][0]) if row.get("a") else None
                vol = float(row["v"][1]) if row.get("v") else 0.0
            except (TypeError, ValueError, KeyError, IndexError):
                continue
            tickers[app] = {"last": last, "bid": bid, "ask": ask, "volume": vol, "ts": None}
        self._tickers = tickers

    def _fetch_ohlcv(self, native_id: str, timeframe: str, lookback: int) -> list[Bar]:
        interval = self._TF_MIN.get(timeframe.lower(), 15)
        url = f"{self._BASE}/OHLC?pair={urllib.parse.quote(native_id)}&interval={interval}"
        data = _http_json(url)
        result = (data or {}).get("result") or {}
        rows = []
        for k, v in result.items():
            if k == "last":
                continue
            if isinstance(v, list):
                rows = v
                break
        app = None
        for a, n in self._native.items():
            if n == native_id:
                app = a
                break
        app = app or normalize_crypto_app_symbol(native_id.replace("XBT", "BTC"))
        out: list[Bar] = []
        for row in rows[-lookback:]:
            try:
                ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
                o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                vol = float(row[6])
            except (TypeError, ValueError, IndexError):
                continue
            out.append(
                stamp_bar_defaults(
                    Bar(
                        ts=ts,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=vol,
                        trades=int(row[7]) if len(row) > 7 else 0,
                        symbol=app,
                        timeframe=timeframe.lower(),
                        data_source_kind=DataSourceKind.LIVE.value,
                        provider=self.provider_id,
                        environment_origin=EnvironmentOrigin.LIVE.value,
                        received_at=datetime.now(timezone.utc),
                    ),
                    provider=self.provider_id,
                    origin=EnvironmentOrigin.LIVE,
                    timeframe=timeframe.lower(),
                )
            )
        return out


class FailoverCryptoProvider:
    """Try public exchanges in order (ccxt-style multi-venue). No mock fallback."""

    provider_id = "crypto_failover"
    display_name = "Crypto Public Failover (OKX→Gate→Kraken→…)"
    is_stub = False
    is_real_provider = True
    kind = DataSourceKind.LIVE
    market_type = MarketType.CRYPTO

    def __init__(self, providers: list[Any]) -> None:
        self._providers = list(providers)
        self.active: Any | None = None
        self._last_error = ""

    def tick(self) -> None:
        self.active = None
        errors: list[str] = []
        for p in self._providers:
            try:
                p.tick()
                if p.has_market_data():
                    self.active = p
                    self.provider_id = f"failover:{getattr(p, 'provider_id', type(p).__name__)}"
                    self.display_name = f"Failover → {getattr(p, 'display_name', p.provider_id)}"
                    self._last_error = ""
                    return
                errors.append(f"{getattr(p, 'provider_id', '?')}:no_data")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{getattr(p, 'provider_id', '?')}:{type(exc).__name__}")
        self._last_error = "; ".join(errors) or "all_providers_failed"

    def _need(self) -> Any:
        if self.active is None or not self.active.has_market_data():
            self.tick()
        if self.active is None:
            raise RuntimeError(f"NO_MARKET_DATA: failover exhausted ({self._last_error})")
        return self.active

    def list_symbols(self) -> list[str]:
        try:
            return self._need().list_symbols()
        except Exception:  # noqa: BLE001
            return []

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return self._need().get_quote(symbol)

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return self._need().get_bars(symbol, lookback)

    def get_bars_tf(self, symbol: str, timeframe: str, lookback: int = 220) -> list[Bar]:
        p = self._need()
        fn = getattr(p, "get_bars_tf", None)
        if callable(fn):
            return fn(symbol, timeframe, lookback=lookback)
        return p.get_bars(symbol, lookback)

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return bool(self.active and self.active.is_fresh(max_age_sec))

    def has_market_data(self) -> bool:
        return bool(self.active and self.active.has_market_data())

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        if self.active:
            meta = self.active.source_meta(max_age_sec)
            return meta
        return build_source_meta(
            provider_id=self.provider_id,
            kind=DataSourceKind.UNAVAILABLE,
            display_name=self.display_name,
            connected=False,
            last_update=None,
            max_age_sec=max_age_sec,
            live_ready=False,
            note=self._last_error or "failover not connected",
        )

    def provenance(self) -> dict[str, str]:
        if self.active and hasattr(self.active, "provenance"):
            return self.active.provenance()
        return crypto_provenance_fields(provider_id=self.provider_id, data_source_kind=DataSourceKind.UNAVAILABLE)

    def health_dict(self) -> dict[str, Any]:
        base = {
            "provider": self.provider_id,
            "failover_chain": [getattr(p, "provider_id", "?") for p in self._providers],
            "active": getattr(self.active, "provider_id", None),
            "errors": [self._last_error] if self._last_error else [],
            "live_trading": False,
            "note": "Public multi-venue failover (GitHub/ccxt-style sources)",
        }
        if self.active and hasattr(self.active, "health_dict"):
            h = self.active.health_dict()
            h.update(base)
            return h
        return {**base, "connected": False, "ohlcv_ready": False, "rest": False}

    def list_markets(self) -> list[CryptoMarketInfo]:
        if self.active and hasattr(self.active, "list_markets"):
            return self.active.list_markets()
        return []

    def ticker_stats(self, symbol: str) -> dict[str, Any]:
        if self.active and hasattr(self.active, "ticker_stats"):
            return self.active.ticker_stats(symbol)
        return {}

    def bid_ask_known(self, symbol: str) -> bool:
        if self.active and hasattr(self.active, "bid_ask_known"):
            return self.active.bid_ask_known(symbol)
        return False

    def quote_spread_pct(self, quote: QuoteSnapshot) -> float | None:
        if self.active and hasattr(self.active, "quote_spread_pct"):
            return self.active.quote_spread_pct(quote)
        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            return None
        return compute_spread_pct(float(quote.bid), float(quote.ask))

    def close(self) -> None:
        for p in self._providers:
            close = getattr(p, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass


def build_public_provider(exchange: str) -> _PublicExchangeBase:
    key = (exchange or "okx").strip().lower()
    if key in {"okx", "okex"}:
        return OkxPublicProvider()
    if key in {"gate", "gateio", "gate_io"}:
        return GatePublicProvider()
    if key in {"kraken"}:
        return KrakenPublicProvider()
    raise ValueError(f"Unsupported public crypto exchange: {exchange!r}")


def build_failover_chain(names: list[str]) -> FailoverCryptoProvider:
    providers: list[Any] = []
    for n in names:
        key = n.strip().lower()
        if not key:
            continue
        if key == "paribu":
            continue  # wired separately by factory when enabled
        try:
            providers.append(build_public_provider(key))
        except ValueError:
            log.warning("skip unknown failover venue %s", key)
    if not providers:
        providers = [OkxPublicProvider(), GatePublicProvider(), KrakenPublicProvider()]
    return FailoverCryptoProvider(providers)
