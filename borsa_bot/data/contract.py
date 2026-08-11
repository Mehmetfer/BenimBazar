"""Canonical market-data contract — foundation for future BIST provider.

Does NOT fetch real data. Does NOT change strategy/AI/broker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from config.models import Bar, QuoteSnapshot
from data.integrity import DataSourceKind, MarketSession, bist_session_now
from data.provenance import parse_data_source_kind


# --- Timeframes ---

BASE_TIMEFRAME = "15m"
REQUIRED_TIMEFRAMES = ("15m", "30m", "1h", "1d")
OPTIONAL_TIMEFRAMES = ("1m", "5m")
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}
REQUIRED_HISTORY_BARS_15M = 240
INDEX_SYMBOL = "XU100"


class EnvironmentOrigin(str, Enum):
    """Where the record originated — distinct from feed subtype (DELAYED/BROKER).

    LIVE here means 'from a real market-data path', not APP_ENV=PRODUCTION.
    """

    LIVE = "LIVE"
    SIMULATED = "SIMULATED"
    TEST = "TEST"
    UNKNOWN = "UNKNOWN"


class DataQuality(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"


@dataclass(frozen=True)
class ContractCheck:
    ok: bool
    quality: DataQuality
    note: str
    tradeable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "quality": self.quality.value,
            "note": self.note,
            "tradeable": self.tradeable,
        }


def ensure_utc(ts: datetime | None) -> datetime | None:
    """Require timezone-aware UTC. Naive → treat as UTC then mark for reject upstream."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return None  # naive rejected by callers
    return ts.astimezone(timezone.utc)


def is_future_timestamp(ts: datetime, *, now: datetime | None = None, skew_sec: float = 5.0) -> bool:
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        return True  # naive treated as invalid/future-reject path
    age = (now - ts.astimezone(timezone.utc)).total_seconds()
    return age < -skew_sec


def compute_spread_pct(bid: float, ask: float) -> float | None:
    """Canonical spread metadata. Midpoint <= 0 → None (do not invent)."""
    if bid is None or ask is None:
        return None
    if not (isinstance(bid, (int, float)) and isinstance(ask, (int, float))):
        return None
    if not math.isfinite(float(bid)) or not math.isfinite(float(ask)):
        return None
    if float(bid) <= 0 or float(ask) <= 0:
        return None
    if float(ask) < float(bid):
        return None
    mid = (float(bid) + float(ask)) / 2.0
    if mid <= 0:
        return None
    return ((float(ask) - float(bid)) / mid) * 100.0


def normalize_app_symbol(raw: str | None) -> str:
    """Provider formats → application symbol. Strategy/UI see only app symbols."""
    if not raw:
        return ""
    s = str(raw).strip().upper()
    for prefix in ("BIST:", "BIST-", "TR:", "ISE:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    if s.endswith(".IS"):
        s = s[:-3]
    if s.endswith(".E"):
        s = s[:-2]
    # XU100 aliases
    if s in {"XU100", "BIST100", "XUTUM", "BIST-100"}:
        return INDEX_SYMBOL
    return s.replace("/", "").replace(" ", "")


def to_provider_symbol(app_symbol: str, style: str = "raw") -> str:
    """Map app symbol to provider-specific form (adapter use only)."""
    sym = normalize_app_symbol(app_symbol)
    style = (style or "raw").lower()
    if style in {"raw", "app"}:
        return sym
    if style in {"yahoo", ".is"}:
        return f"{sym}.IS" if sym != INDEX_SYMBOL else "XU100.IS"
    if style in {"bist:", "prefixed"}:
        return f"BIST:{sym}"
    return sym


def is_index_symbol(symbol: str | None) -> bool:
    return normalize_app_symbol(symbol) == INDEX_SYMBOL


def is_valid_timeframe(tf: str | None) -> bool:
    return (tf or "").lower() in TIMEFRAME_MINUTES


def validate_ohlcv_values(
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> ContractCheck:
    for name, v in (("open", open_), ("high", high), ("low", low), ("close", close)):
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or float(v) <= 0:
            return ContractCheck(False, DataQuality.INVALID, f"invalid {name}")
    if volume is None or not isinstance(volume, (int, float)) or not math.isfinite(float(volume)) or float(volume) < 0:
        return ContractCheck(False, DataQuality.INVALID, "invalid volume")
    o, h, l, c = float(open_), float(high), float(low), float(close)
    if not (h >= o and h >= c and h >= l):
        return ContractCheck(False, DataQuality.INVALID, "high constraint failed")
    if not (l <= o and l <= c and l <= h):
        return ContractCheck(False, DataQuality.INVALID, "low constraint failed")
    return ContractCheck(True, DataQuality.VALID, "ohlcv ok", tradeable=False)


def validate_canonical_bar(bar: Bar | None, *, require_symbol: bool = False) -> ContractCheck:
    if bar is None:
        return ContractCheck(False, DataQuality.UNAVAILABLE, "bar is None")
    sym = getattr(bar, "symbol", None) or ""
    if require_symbol and not normalize_app_symbol(sym):
        return ContractCheck(False, DataQuality.INVALID, "invalid symbol")
    ts = getattr(bar, "ts", None)
    if ts is None:
        return ContractCheck(False, DataQuality.INVALID, "missing timestamp")
    if not isinstance(ts, datetime) or ts.tzinfo is None:
        return ContractCheck(False, DataQuality.INVALID, "timestamp must be UTC-aware")
    if is_future_timestamp(ts):
        return ContractCheck(False, DataQuality.INVALID, "future timestamp REJECT")
    tf = getattr(bar, "timeframe", None) or BASE_TIMEFRAME
    if not is_valid_timeframe(tf):
        return ContractCheck(False, DataQuality.INVALID, f"invalid timeframe={tf}")
    kind = parse_data_source_kind(getattr(bar, "data_source_kind", None))
    if kind == DataSourceKind.UNKNOWN:
        return ContractCheck(False, DataQuality.UNKNOWN_SOURCE, "UNKNOWN source — NOT TRADEABLE")
    ohlc = validate_ohlcv_values(
        open_=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume
    )
    if not ohlc.ok:
        return ohlc
    return ContractCheck(True, DataQuality.VALID, "bar valid")


def validate_canonical_quote(
    quote: QuoteSnapshot | None,
    *,
    max_age_sec: float = 30.0,
    now: datetime | None = None,
) -> ContractCheck:
    if quote is None:
        return ContractCheck(False, DataQuality.UNAVAILABLE, "quote is None")
    sym = normalize_app_symbol(getattr(quote, "symbol", None))
    if not sym:
        return ContractCheck(False, DataQuality.INVALID, "invalid symbol")
    price = getattr(quote, "price", None)
    if price is None or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
        return ContractCheck(False, DataQuality.INVALID, "invalid price")
    ts = getattr(quote, "ts", None)
    if ts is None or not isinstance(ts, datetime) or ts.tzinfo is None:
        return ContractCheck(False, DataQuality.INVALID, "timestamp must be UTC-aware")
    if is_future_timestamp(ts, now=now):
        return ContractCheck(False, DataQuality.INVALID, "future timestamp REJECT")
    now = now or datetime.now(timezone.utc)
    age = (now - ts.astimezone(timezone.utc)).total_seconds()
    if age > max_age_sec:
        return ContractCheck(False, DataQuality.STALE, f"stale age={int(age)}s", tradeable=False)

    bid = float(getattr(quote, "bid", 0) or 0)
    ask = float(getattr(quote, "ask", 0) or 0)
    if bid <= 0:
        return ContractCheck(False, DataQuality.INVALID, "invalid bid")
    if ask <= 0:
        return ContractCheck(False, DataQuality.INVALID, "invalid ask")
    if ask < bid:
        return ContractCheck(False, DataQuality.INVALID, "ask < bid")

    kind = parse_data_source_kind(getattr(quote, "data_source_kind", None))
    if kind == DataSourceKind.UNKNOWN:
        return ContractCheck(False, DataQuality.UNKNOWN_SOURCE, "UNKNOWN source")

    status = getattr(quote, "market_status", None) or MarketSession.UNKNOWN.value
    if str(status).upper() == MarketSession.UNKNOWN.value:
        return ContractCheck(False, DataQuality.INVALID, "UNKNOWN market status — NOT TRADEABLE")

    # Only LIVE feed kind can be tradeable when fresh+valid
    tradeable = kind == DataSourceKind.LIVE
    return ContractCheck(True, DataQuality.VALID, "quote valid", tradeable=tradeable)


def dedupe_bars(bars: Sequence[Bar]) -> list[Bar]:
    """Keep last bar per UTC timestamp; reject duplicates by collapsing."""
    by_ts: dict[str, Bar] = {}
    for b in bars:
        ts = getattr(b, "ts", None)
        if ts is None or not isinstance(ts, datetime) or ts.tzinfo is None:
            continue
        key = ts.astimezone(timezone.utc).isoformat()
        by_ts[key] = b
    out = list(by_ts.values())
    out.sort(key=lambda x: x.ts.astimezone(timezone.utc))
    return out


def sort_bars_safe(bars: Sequence[Bar]) -> list[Bar]:
    """Out-of-order → sorted ascending by UTC ts. Invalid/naive dropped."""
    valid = []
    for b in bars:
        ts = getattr(b, "ts", None)
        if ts is None or not isinstance(ts, datetime) or ts.tzinfo is None:
            continue
        if is_future_timestamp(ts):
            continue
        valid.append(b)
    valid.sort(key=lambda x: x.ts.astimezone(timezone.utc))
    return dedupe_bars(valid)


def check_history(
    bars: Sequence[Bar] | None,
    *,
    min_bars: int = REQUIRED_HISTORY_BARS_15M,
    timeframe: str = BASE_TIMEFRAME,
) -> ContractCheck:
    if not bars:
        return ContractCheck(False, DataQuality.INSUFFICIENT_HISTORY, "no bars", tradeable=False)
    cleaned = sort_bars_safe(bars)
    if len(cleaned) < min_bars:
        return ContractCheck(
            False,
            DataQuality.INSUFFICIENT_HISTORY,
            f"need >={min_bars} × {timeframe}, got {len(cleaned)} — do not pad with mock",
            tradeable=False,
        )
    return ContractCheck(True, DataQuality.VALID, f"history ok n={len(cleaned)}")


def stamp_quote_defaults(quote: QuoteSnapshot, *, provider: str, origin: EnvironmentOrigin) -> QuoteSnapshot:
    """Fill canonical optional fields without inventing prices."""
    if not getattr(quote, "provider", None):
        quote.provider = provider
    if not getattr(quote, "environment_origin", None) or quote.environment_origin == "UNKNOWN":
        quote.environment_origin = origin.value
    status = str(getattr(quote, "market_status", None) or "UNKNOWN").upper()
    if status in {"", "UNKNOWN"}:
        quote.market_status = bist_session_now().value
    if getattr(quote, "received_at", None) is None:
        quote.received_at = datetime.now(timezone.utc)
    # Normalize symbol to app form
    quote.symbol = normalize_app_symbol(quote.symbol)
    return quote


def stamp_bar_defaults(
    bar: Bar,
    *,
    provider: str,
    origin: EnvironmentOrigin,
    symbol: str | None = None,
    timeframe: str = BASE_TIMEFRAME,
) -> Bar:
    if symbol:
        bar.symbol = normalize_app_symbol(symbol)
    elif getattr(bar, "symbol", None):
        bar.symbol = normalize_app_symbol(bar.symbol)
    if not getattr(bar, "provider", None):
        bar.provider = provider
    if not getattr(bar, "environment_origin", None) or bar.environment_origin == "UNKNOWN":
        bar.environment_origin = origin.value
    if not getattr(bar, "timeframe", None):
        bar.timeframe = timeframe
    if getattr(bar, "received_at", None) is None:
        bar.received_at = datetime.now(timezone.utc)
    return bar
