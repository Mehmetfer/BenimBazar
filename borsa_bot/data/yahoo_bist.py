"""Yahoo Finance public BIST market data — real prices, fail-closed.

Uses query1.finance.yahoo.com (THYAO.IS, XU100.IS). No invented prices.
During BIST session: DELAYED public feed (~15m). Paper/dev observation only.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config.models import Bar, QuoteSnapshot
from data.contract import (
    BASE_TIMEFRAME,
    EnvironmentOrigin,
    INDEX_SYMBOL,
    REQUIRED_HISTORY_BARS_15M,
    normalize_app_symbol,
    stamp_bar_defaults,
    stamp_quote_defaults,
    to_provider_symbol,
)
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, bist_session_now, build_source_meta

logger = logging.getLogger("borsa_bot.market_data")

_UA = "borsa-bot/yahoo-bist (+https://github.com/Mehmetfer/Koca_Kafa)"
# Yahoo BIST snapshots are typically ~15m delayed — freshness gate must not use 30s.
_DELAYED_MAX_AGE_SEC = 1200.0


def _default_symbols() -> list[str]:
    from universe.bist100 import get_company, list_companies

    syms = [c.ticker for c in list_companies()]
    if INDEX_SYMBOL not in syms:
        syms.insert(0, INDEX_SYMBOL)
    return sorted(set(syms))


def _sector_for(sym: str) -> str:
    from universe.bist100 import get_company
    from universe.tradeable import get_instrument

    c = get_company(sym)
    if c:
        return c.sector
    inst = get_instrument(sym)
    return inst.sector if inst else ""


def _name_for(sym: str) -> str:
    from universe.bist100 import get_company
    from universe.tradeable import get_instrument

    c = get_company(sym)
    if c:
        return c.name
    inst = get_instrument(sym)
    return inst.name if inst else sym


class YahooBistMarketDataProvider:
    """Real Yahoo Finance BIST feed. kind=DELAYED (honest — not exchange-tick LIVE)."""

    provider_id = "yahoo_bist"
    kind = DataSourceKind.DELAYED
    display_name = "Yahoo Finance BIST (public DELAYED)"
    is_stub = False
    is_real_provider = True

    def __init__(self, symbols: list[str] | None = None, *, timeout_sec: float = 4.0) -> None:
        self.timeout_sec = timeout_sec
        self._symbols = list(symbols) if symbols else _default_symbols()
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._bars: dict[str, list[Bar]] = {}
        self._last_ok: datetime | None = None
        self._connected = False
        self._error = ""
        self._rate_limited_until: float = 0.0

    def _rate_limited(self) -> bool:
        return time.time() < self._rate_limited_until

    def _mark_rate_limited(self, sec: float = 45.0) -> None:
        self._rate_limited_until = time.time() + sec
        self._error = "YAHOO_RATE_LIMITED"

    def _get_json(self, url: str) -> Any:
        if self._rate_limited():
            raise RuntimeError("YAHOO_RATE_LIMITED")
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:  # noqa: S310
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) == 429:
                self._mark_rate_limited(60.0)
                raise RuntimeError("YAHOO_RATE_LIMITED") from exc
            raise

    def _fetch_quotes_batch(self, symbols: list[str]) -> None:
        if not symbols:
            return
        yahoo_syms = ",".join(to_provider_symbol(s, "yahoo") for s in symbols)
        url = (
            "https://query1.finance.yahoo.com/v8/finance/spark"
            f"?symbols={urllib.parse.quote(yahoo_syms, safe=',')}&interval=15m&range=1d"
        )
        data = self._get_json(url)
        if not isinstance(data, dict):
            raise RuntimeError("invalid spark payload")
        session = bist_session_now()
        now = datetime.now(timezone.utc)
        for ysym, block in data.items():
            if not isinstance(block, dict):
                continue
            app_sym = normalize_app_symbol(str(block.get("symbol") or ysym).replace(".IS", ""))
            closes = block.get("close") or []
            timestamps = block.get("timestamp") or []
            if not closes:
                continue
            price = float(closes[-1])
            if price <= 0:
                continue
            ts_raw = timestamps[-1] if timestamps else None
            ts = (
                datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                if ts_raw is not None
                else now
            )
            spread = max(0.01, price * 0.0008)
            change_pct = 0.0
            if len(closes) >= 2 and closes[-2]:
                try:
                    change_pct = (float(closes[-1]) / float(closes[-2]) - 1.0) * 100.0
                except (TypeError, ValueError, ZeroDivisionError):
                    change_pct = 0.0
            q = QuoteSnapshot(
                symbol=app_sym,
                name=_name_for(app_sym),
                sector=_sector_for(app_sym),
                price=round(price, 4),
                bid=round(price - spread / 2, 4),
                ask=round(price + spread / 2, 4),
                volume=0.0,
                trades=0,
                ts=ts,
                data_source_kind=DataSourceKind.DELAYED.value,
                provider=self.provider_id,
                environment_origin=EnvironmentOrigin.LIVE.value,
                market_status=session.value,
                received_at=now,
            )
            self._quotes[app_sym] = stamp_quote_defaults(
                q,
                provider=self.provider_id,
                origin=EnvironmentOrigin.LIVE,
            )
            setattr(self._quotes[app_sym], "change_pct", round(change_pct, 2))

    def _fetch_bars(self, symbol: str, lookback: int) -> list[Bar]:
        sym = normalize_app_symbol(symbol)
        ysym = to_provider_symbol(sym, "yahoo")
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(ysym)}?interval=15m&range=60d"
        )
        data = self._get_json(url)
        result = ((data or {}).get("chart") or {}).get("result") or []
        if not result:
            raise RuntimeError(f"empty chart for {sym}")
        block = result[0]
        timestamps = block.get("timestamp") or []
        quote = (block.get("indicators") or {}).get("quote") or [{}]
        q0 = quote[0] if quote else {}
        opens = q0.get("open") or []
        highs = q0.get("high") or []
        lows = q0.get("low") or []
        closes = q0.get("close") or []
        vols = q0.get("volume") or []
        bars: list[Bar] = []
        now = datetime.now(timezone.utc)
        for i, ts_raw in enumerate(timestamps):
            try:
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                if None in (o, h, l, c) or float(c) <= 0:
                    continue
                vol = float(vols[i] or 0) if i < len(vols) else 0.0
                bar = Bar(
                    ts=datetime.fromtimestamp(float(ts_raw), tz=timezone.utc),
                    open=round(float(o), 4),
                    high=round(float(h), 4),
                    low=round(float(l), 4),
                    close=round(float(c), 4),
                    volume=vol,
                    trades=0,
                    data_source_kind=DataSourceKind.DELAYED.value,
                    symbol=sym,
                    timeframe=BASE_TIMEFRAME,
                    provider=self.provider_id,
                    environment_origin=EnvironmentOrigin.LIVE.value,
                    received_at=now,
                )
                bars.append(
                    stamp_bar_defaults(
                        bar,
                        provider=self.provider_id,
                        origin=EnvironmentOrigin.LIVE,
                        symbol=sym,
                        timeframe=BASE_TIMEFRAME,
                    )
                )
            except (TypeError, ValueError, IndexError):
                continue
        bars.sort(key=lambda b: b.ts)
        if not bars:
            raise RuntimeError(f"no valid bars for {sym}")
        self._bars[sym] = bars
        return bars[-lookback:]

    def tick(self) -> None:
        if bist_session_now() != MarketSession.OPEN:
            self._error = "BIST session CLOSED — Yahoo tick skipped"
            # Keep last quotes if any; do not mark disconnected when we have cache
            if self._quotes:
                return
            self._connected = False
            return
        if self._rate_limited():
            # Keep last good quotes — do not hammer Yahoo
            if self._quotes:
                self._connected = True
                return
            self._connected = False
            return
        try:
            chunk = 18
            for i in range(0, len(self._symbols), chunk):
                if self._rate_limited():
                    break
                self._fetch_quotes_batch(self._symbols[i : i + chunk])
                time.sleep(0.15)
            if not self._quotes:
                raise RuntimeError("no quotes returned")
            self._connected = True
            self._last_ok = datetime.now(timezone.utc)
            if not self._rate_limited():
                self._error = ""
        except Exception as exc:  # noqa: BLE001
            if "RATE_LIMITED" in str(exc):
                if self._quotes:
                    self._connected = True
                    logger.warning("YahooBist rate-limited — serving cached quotes")
                    return
            self._connected = False
            self._error = f"YAHOO_FETCH_FAILED:{type(exc).__name__}"
            logger.warning("YahooBist tick failed: %s", exc)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        sym = normalize_app_symbol(symbol)
        if sym not in self._quotes:
            if bist_session_now() == MarketSession.OPEN:
                self._fetch_quotes_batch([sym])
            if sym not in self._quotes:
                raise RuntimeError(f"NO_MARKET_DATA: no Yahoo quote for {sym}")
        return self._quotes[sym]

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        sym = normalize_app_symbol(symbol)
        need = max(lookback, REQUIRED_HISTORY_BARS_15M)
        cached = self._bars.get(sym)
        if cached and len(cached) >= need:
            return cached[-lookback:]
        if cached:
            # Prefer stale/partial cache over blocking on rate limit
            if self._rate_limited():
                return cached[-lookback:]
        if self._rate_limited():
            raise RuntimeError(f"NO_MARKET_DATA: Yahoo rate-limited ({sym})")
        try:
            return self._fetch_bars(sym, lookback)
        except Exception:
            if cached:
                return cached[-lookback:]
            raise

    def list_symbols(self) -> list[str]:
        return [s for s in self._symbols if s != INDEX_SYMBOL]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        if not self._last_ok:
            return False
        limit = max(float(max_age_sec), _DELAYED_MAX_AGE_SEC)
        return (datetime.now(timezone.utc) - self._last_ok).total_seconds() <= limit

    def has_market_data(self) -> bool:
        if bist_session_now() != MarketSession.OPEN:
            return bool(self._quotes)
        return self._connected and bool(self._quotes) and not self._error.startswith("YAHOO_FETCH_FAILED")

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        session = bist_session_now()
        note = self._error or (
            f"Yahoo BIST DELAYED · {len(self._quotes)} quotes · session={session.value}"
            if self._connected
            else "Yahoo BIST not connected"
        )
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self.kind if self._connected else DataSourceKind.REQUIRED,
            display_name=self.display_name,
            connected=self.has_market_data(),
            last_update=self._last_ok,
            max_age_sec=max(float(max_age_sec), _DELAYED_MAX_AGE_SEC),
            live_ready=False,
            note=note,
        )
