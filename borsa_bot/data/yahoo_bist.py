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

    def tick(self, allow_closed: bool = False) -> None:
        session = bist_session_now()
        closed = session != MarketSession.OPEN
        if closed and not allow_closed:
            self._error = "BIST session CLOSED — Yahoo tick skipped"
            # Keep last quotes if any; do not mark disconnected when we have cache
            if self._quotes:
                return
            self._connected = False
            return
        if closed and allow_closed and self._quotes and self._last_ok:
            age = (datetime.now(timezone.utc) - self._last_ok).total_seconds()
            # Off-hours: reuse last board for 15m to avoid Yahoo hammering
            if age < 900:
                self._connected = True
                self._error = "BIST CLOSED — serving cached last quotes"
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
            if closed and allow_closed:
                self._error = "BIST CLOSED — last/delayed Yahoo quotes"
            elif not self._rate_limited():
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

    def get_quote(self, symbol: str, allow_closed: bool = False) -> QuoteSnapshot:
        sym = normalize_app_symbol(symbol)
        if sym not in self._quotes:
            session_open = bist_session_now() == MarketSession.OPEN
            if session_open or allow_closed:
                if not self._rate_limited():
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

    def period_returns(self, symbol: str) -> dict[str, float | None]:
        """Daily / monthly / yearly % — thin wrapper over board_market_pack."""
        pack = self.board_market_pack(symbol)
        return {
            "daily_pct": pack.get("daily_pct"),
            "weekly_pct": pack.get("weekly_pct"),
            "monthly_pct": pack.get("monthly_pct"),
            "yearly_pct": pack.get("yearly_pct"),
        }

    def board_market_pack(self, symbol: str) -> dict:
        """Info-style board stats from Yahoo 1d chart + quote meta."""
        sym = normalize_app_symbol(symbol)
        ysym = to_provider_symbol(sym, "yahoo")
        out: dict = {
            "daily_pct": None,
            "weekly_pct": None,
            "monthly_pct": None,
            "yearly_pct": None,
            "change_abs": None,
            "prev_close": None,
            "day_low": None,
            "day_high": None,
            "floor": None,
            "ceiling": None,
            "market_cap": None,
            "market_group": "Yıldız Pazar" if sym != "XU100" else "Endeks",
            "weekly": {"pct": None, "dip": None, "zirve": None},
            "monthly": {"pct": None, "dip": None, "zirve": None},
            "yearly": {"pct": None, "dip": None, "zirve": None},
        }
        q = self._quotes.get(sym)
        last_px = float(q.price) if q is not None else None

        if self._rate_limited():
            if q is not None and getattr(q, "change_pct", None) is not None:
                # Only as last resort — spark 15m change is unreliable for daily %
                out["daily_pct"] = round(float(q.change_pct), 2)
            return out
        try:
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{urllib.parse.quote(ysym)}?interval=1d&range=1y"
            )
            data = self._get_json(url)
            result = ((data or {}).get("chart") or {}).get("result") or []
            if not result:
                return out
            block = result[0] or {}
            meta = block.get("meta") or {}
            q0 = (((block.get("indicators") or {}).get("quote") or [{}])[0]) or {}
            closes_raw = q0.get("close") or []
            highs_raw = q0.get("high") or []
            lows_raw = q0.get("low") or []
            closes: list[float] = []
            highs: list[float] = []
            lows: list[float] = []
            for i, c in enumerate(closes_raw):
                if c is None or float(c) <= 0:
                    continue
                closes.append(float(c))
                h = highs_raw[i] if i < len(highs_raw) else c
                l = lows_raw[i] if i < len(lows_raw) else c
                highs.append(float(h) if h is not None else float(c))
                lows.append(float(l) if l is not None else float(c))
            if not closes:
                return out
            last = closes[-1]
            if last_px is None:
                last_px = last
            # For range=1y, Yahoo chartPreviousClose is often the year-ago ref — wrong for daily %.
            # Prefer prior daily bar close; accept meta only if near last price.
            prev = closes[-2] if len(closes) >= 2 else None
            meta_prev = None
            for key in ("regularMarketPreviousClose", "previousClose", "chartPreviousClose"):
                v = meta.get(key)
                if v is not None and float(v) > 0:
                    meta_prev = float(v)
                    break
            if meta_prev and last_px and abs(meta_prev / float(last_px) - 1.0) <= 0.12:
                prev = meta_prev
            out["prev_close"] = round(prev, 2) if prev else None
            if prev and prev > 0 and last_px:
                out["daily_pct"] = round((float(last_px) / prev - 1.0) * 100.0, 2)
                out["change_abs"] = round(float(last_px) - prev, 2)
            day_high = meta.get("regularMarketDayHigh")
            day_low = meta.get("regularMarketDayLow")
            # Day range from last daily bar when meta missing / stale
            if highs:
                day_high = day_high if day_high is not None else highs[-1]
            if lows:
                day_low = day_low if day_low is not None else lows[-1]
            # Prefer last bar OHLC when meta day range looks like multi-day
            if highs and lows and day_high is not None and day_low is not None:
                if float(day_high) - float(day_low) > float(last_px or last) * 0.25:
                    day_high, day_low = highs[-1], lows[-1]
            out["day_high"] = round(float(day_high), 2) if day_high else None
            out["day_low"] = round(float(day_low), 2) if day_low else None
            ref = prev or last_px
            if ref and float(ref) > 0:
                # BIST free band ≈ ±10% of reference (prev close)
                out["floor"] = round(float(ref) * 0.90, 2)
                out["ceiling"] = round(float(ref) * 1.10, 2)

            def _range_pack(n: int) -> dict:
                if len(closes) < max(2, n):
                    return {"pct": None, "dip": None, "zirve": None}
                base = closes[-n]
                pct_v = round((last / base - 1.0) * 100.0, 2) if base else None
                window_h = highs[-n:]
                window_l = lows[-n:]
                return {
                    "pct": pct_v,
                    "dip": round(min(window_l), 2) if window_l else None,
                    "zirve": round(max(window_h), 2) if window_h else None,
                }

            weekly = _range_pack(5)
            monthly = _range_pack(22)
            yearly = _range_pack(len(closes))
            out["weekly"] = weekly
            out["monthly"] = monthly
            out["yearly"] = yearly
            out["weekly_pct"] = weekly.get("pct")
            out["monthly_pct"] = monthly.get("pct")
            out["yearly_pct"] = yearly.get("pct")

            mcap = meta.get("marketCap")
            if mcap is None:
                # Secondary quote endpoint (best-effort)
                try:
                    qurl = (
                        "https://query1.finance.yahoo.com/v7/finance/quote"
                        f"?symbols={urllib.parse.quote(ysym)}"
                    )
                    qdata = self._get_json(qurl)
                    results = (((qdata or {}).get("quoteResponse") or {}).get("result")) or []
                    if results:
                        mcap = results[0].get("marketCap")
                        if out["prev_close"] is None and results[0].get("regularMarketPreviousClose"):
                            out["prev_close"] = round(float(results[0]["regularMarketPreviousClose"]), 2)
                        if out["day_high"] is None and results[0].get("regularMarketDayHigh"):
                            out["day_high"] = round(float(results[0]["regularMarketDayHigh"]), 2)
                        if out["day_low"] is None and results[0].get("regularMarketDayLow"):
                            out["day_low"] = round(float(results[0]["regularMarketDayLow"]), 2)
                except Exception:  # noqa: BLE001
                    mcap = None
            if mcap is not None:
                try:
                    out["market_cap"] = int(float(mcap))
                except (TypeError, ValueError):
                    out["market_cap"] = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("board_market_pack failed for %s: %s", sym, exc)
        return out
