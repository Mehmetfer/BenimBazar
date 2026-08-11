"""HTTP live BIST market-data provider — real fetch, fail-closed.

Expected REST contract (MARKET_DATA_URL base):
  GET /v1/health
  GET /v1/symbols
  GET /v1/quote/{symbol}
  GET /v1/bars/{symbol}?timeframe=15m&limit=240

Auth header: Authorization: Bearer <MARKET_DATA_TOKEN>

Never invents prices. On any failure → has_market_data=False → NO TRADE.
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
from data.contract import (
    EnvironmentOrigin,
    INDEX_SYMBOL,
    REQUIRED_HISTORY_BARS_15M,
    normalize_app_symbol,
    stamp_bar_defaults,
    stamp_quote_defaults,
)
from data.integrity import DataSourceKind, DataSourceMeta, MarketSession, bist_session_now, build_source_meta
from universe.tradeable import list_tradeable_symbols

logger = logging.getLogger("borsa_bot.market_data")


def _parse_ts(raw: Any) -> datetime:
    """Parse timestamp — NEVER invent `now` on failure (defeats future/invalid rejection)."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if raw is None:
        raise ValueError("MISSING_TIMESTAMP")
    s = str(raw).replace("Z", "+00:00").strip()
    if not s:
        raise ValueError("EMPTY_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"INVALID_TIMESTAMP:{raw!r}") from exc


class HttpLiveMarketDataProvider:
    """Real HTTP market-data client. is_stub=False when connected with data."""

    provider_id = "http_live"
    kind = DataSourceKind.LIVE
    display_name = "HttpLiveMarketDataProvider"
    is_stub = False
    is_real_provider = True

    def __init__(self, base_url: str, token: str, *, timeout_sec: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_sec = timeout_sec
        self._last_ok: datetime | None = None
        self._connected = False
        self._error = ""
        self._quotes: dict[str, QuoteSnapshot] = {}
        self._bars: dict[str, list[Bar]] = {}
        self._symbols: list[str] = []
        self._kind = DataSourceKind.LIVE

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "borsa-bot/phase2",
        }

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        q = ""
        if params:
            q = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}{q}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:  # noqa: S310 — URL from env
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}

    def tick(self) -> None:
        try:
            # Prefer symbols endpoint; fall back to catalog list for quote fan-out later
            data = self._get_json("/v1/symbols")
            syms: list[str] = []
            if isinstance(data, dict):
                raw = data.get("symbols") or data.get("instruments") or []
            else:
                raw = data
            for item in raw:
                if isinstance(item, str):
                    syms.append(normalize_app_symbol(item))
                elif isinstance(item, dict):
                    s = item.get("symbol") or item.get("ticker")
                    if s:
                        syms.append(normalize_app_symbol(str(s)))
            syms = [s for s in syms if s and s != INDEX_SYMBOL]
            if not syms:
                # Provider reachable but empty — keep catalog for discovery intersection
                syms = list_tradeable_symbols()
            self._symbols = sorted(set(syms))
            # Sample a health/index quote if offered
            try:
                health = self._get_json("/v1/health")
                kind_raw = str((health or {}).get("data_source_kind") or "LIVE").upper()
                if kind_raw in {"LIVE", "DELAYED", "BROKER"}:
                    self._kind = DataSourceKind(kind_raw)
            except Exception:  # noqa: BLE001
                pass
            self._connected = True
            self._last_ok = datetime.now(timezone.utc)
            self._error = ""
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            self._error = f"LIVE_FETCH_FAILED:{type(exc).__name__}"
            logger.warning("HttpLiveMarketDataProvider tick failed: %s", type(exc).__name__)

    def _ensure_quote(self, symbol: str) -> QuoteSnapshot:
        sym = normalize_app_symbol(symbol)
        if sym in self._quotes and self.is_fresh(60):
            return self._quotes[sym]
        data = self._get_json(f"/v1/quote/{urllib.parse.quote(sym)}")
        if not isinstance(data, dict) or not data.get("price"):
            raise RuntimeError(f"NO_MARKET_DATA: empty quote for {sym}")
        kind = str(data.get("data_source_kind") or self._kind.value).upper()
        if kind in {"SIMULATED", "MOCK", "UNKNOWN", "TEST"}:
            raise RuntimeError(f"NO_TRADE: provider returned non-live kind={kind}")
        session = bist_session_now()
        q = QuoteSnapshot(
            symbol=sym,
            name=str(data.get("name") or sym),
            sector=str(data.get("sector") or ""),
            price=float(data["price"]),
            bid=float(data.get("bid") or data["price"]),
            ask=float(data.get("ask") or data["price"]),
            volume=float(data.get("volume") or 0),
            trades=int(data.get("trades") or 0),
            ts=_parse_ts(data.get("timestamp") or data.get("ts")),
            data_source_kind=kind,
            provider=self.provider_id,
            environment_origin=EnvironmentOrigin.LIVE.value,
            market_status=str(data.get("market_status") or session.value),
            received_at=datetime.now(timezone.utc),
        )
        q = stamp_quote_defaults(q, provider=self.provider_id, kind=kind, origin=EnvironmentOrigin.LIVE)
        self._quotes[sym] = q
        self._connected = True
        self._last_ok = datetime.now(timezone.utc)
        return q

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        try:
            return self._ensure_quote(symbol)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            raise RuntimeError(f"NO_MARKET_DATA: {exc}") from exc

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        sym = normalize_app_symbol(symbol)
        try:
            data = self._get_json(
                f"/v1/bars/{urllib.parse.quote(sym)}",
                {"timeframe": "15m", "limit": max(lookback, REQUIRED_HISTORY_BARS_15M)},
            )
            rows = data.get("bars") if isinstance(data, dict) else data
            bars: list[Bar] = []
            kind = self._kind.value
            for row in rows or []:
                bars.append(
                    stamp_bar_defaults(
                        Bar(
                            ts=_parse_ts(row.get("ts") or row.get("timestamp")),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row.get("volume") or 0),
                            trades=int(row.get("trades") or 0),
                            symbol=sym,
                            timeframe=str(row.get("timeframe") or "15m"),
                            data_source_kind=str(row.get("data_source_kind") or kind),
                            provider=self.provider_id,
                            environment_origin=EnvironmentOrigin.LIVE.value,
                            received_at=datetime.now(timezone.utc),
                        ),
                        provider=self.provider_id,
                        kind=str(row.get("data_source_kind") or kind),
                        origin=EnvironmentOrigin.LIVE,
                    )
                )
            bars.sort(key=lambda b: b.ts)
            self._bars[sym] = bars
            self._last_ok = datetime.now(timezone.utc)
            return bars[-lookback:]
        except Exception as exc:  # noqa: BLE001
            # Fail-closed: do NOT silently serve possibly stale cache as live data
            self._error = f"bars:{exc}"
            raise RuntimeError(f"NO_MARKET_DATA bars: {exc}") from exc

    def list_symbols(self) -> list[str]:
        if self._symbols:
            return list(self._symbols)
        # Fail-closed listing: catalog discovery is OK for names; quotes still require fetch
        return list_tradeable_symbols()

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        if not self._last_ok:
            return False
        return (datetime.now(timezone.utc) - self._last_ok).total_seconds() <= max_age_sec

    def has_market_data(self) -> bool:
        return self._connected and not self._error.startswith("LIVE_FETCH_FAILED")

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return build_source_meta(
            provider_id=self.provider_id,
            kind=self._kind if self._connected else DataSourceKind.REQUIRED,
            display_name=self.display_name,
            connected=self._connected,
            last_update=self._last_ok,  # datetime — never isoformat string
            max_age_sec=max_age_sec,
            live_ready=bool(self._connected and self._kind == DataSourceKind.LIVE),
            note=self._error or ("LIVE connected" if self._connected else "not connected"),
        )


class CatalogListProvider:
    """DEV helper: expose full catalog symbols for discovery tests without inventing prices.

    has_market_data follows the wrapped provider. list_symbols uses tradeable catalog.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        for attr in ("provider_id", "kind", "display_name", "is_stub", "is_real_provider"):
            setattr(self, attr, getattr(inner, attr, None))

    def list_symbols(self) -> list[str]:
        # Prefer live symbols when available
        try:
            live = list(self.inner.list_symbols())
            if live and getattr(self.inner, "has_market_data", lambda: False)():
                return live
        except Exception:  # noqa: BLE001
            pass
        return list_tradeable_symbols()

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return self.inner.get_bars(symbol, lookback)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return self.inner.get_quote(symbol)

    def tick(self) -> None:
        return self.inner.tick()

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return self.inner.is_fresh(max_age_sec)

    def has_market_data(self) -> bool:
        return self.inner.has_market_data()

    def source_meta(self, max_age_sec: float = 30.0) -> DataSourceMeta:
        return self.inner.source_meta(max_age_sec)
