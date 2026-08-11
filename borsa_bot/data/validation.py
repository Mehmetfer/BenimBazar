"""Production market-data hard block — fail closed, no mock fallback.

Does not change BUY/STRONG BUY math. Only gates whether any market data
may enter the trading pipeline.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from config.models import Bar, QuoteSnapshot
from data.integrity import DataSourceKind, DataSourceMeta, FreshnessStatus, MarketSession

log = logging.getLogger("borsa_bot.market_data")

# Names / kinds that must never feed PRODUCTION trading
_BLOCKED_PROVIDER_TOKENS = frozenset(
    {
        "mock",
        "simulated",
        "sim",
        "demo",
        "fake",
        "synthetic",
        "dummy",
        "placeholder",
        "random",
        "generated",
        "paper",  # paper provider alias maps to SimulatedProvider
        "test",
        "sample",
    }
)

_BLOCKED_KINDS_PRODUCTION = frozenset(
    {
        DataSourceKind.SIMULATED,
        DataSourceKind.UNAVAILABLE,
    }
)

_VERIFIED_KINDS = frozenset(
    {
        DataSourceKind.LIVE,
        DataSourceKind.DELAYED,
        DataSourceKind.BROKER,
    }
)


class AppEnvironment(str, Enum):
    PRODUCTION = "PRODUCTION"
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"


class MarketDataGateCode(str, Enum):
    OK = "OK"
    PRODUCTION_MARKET_DATA_VIOLATION = "PRODUCTION_MARKET_DATA_VIOLATION"
    NO_MARKET_DATA = "NO_MARKET_DATA"
    INVALID_MARKET_DATA = "INVALID_MARKET_DATA"
    STALE_DATA = "STALE_DATA"
    DATA_NOT_VERIFIED = "DATA_NOT_VERIFIED"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"


class ProductionMarketDataViolation(RuntimeError):
    """Raised when PRODUCTION would use mock/simulated/fake market data."""

    code = MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION.value


@dataclass(frozen=True)
class MarketDataGateResult:
    ok: bool
    code: MarketDataGateCode
    signals_allowed: bool
    note: str
    environment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code.value,
            "signals_allowed": self.signals_allowed,
            "note": self.note,
            "environment": self.environment,
            "ui_message": (
                "MARKET DATA UNAVAILABLE"
                if not self.signals_allowed
                else "OK"
            ),
        }


def normalize_app_env(raw: str | None) -> AppEnvironment:
    key = (raw or "DEVELOPMENT").strip().upper()
    aliases = {
        "PROD": AppEnvironment.PRODUCTION,
        "PRODUCTION": AppEnvironment.PRODUCTION,
        "DEV": AppEnvironment.DEVELOPMENT,
        "DEVELOPMENT": AppEnvironment.DEVELOPMENT,
        "DEVELOP": AppEnvironment.DEVELOPMENT,
        "TEST": AppEnvironment.TEST,
        "TESTING": AppEnvironment.TEST,
        "CI": AppEnvironment.TEST,
    }
    return aliases.get(key, AppEnvironment.DEVELOPMENT)


def is_blocked_provider_name(name: str | None) -> bool:
    key = (name or "").strip().lower()
    if not key:
        return True
    if key in _BLOCKED_PROVIDER_TOKENS:
        return True
    # Match blocked tokens as whole path segments only (avoid "test" in "contest")
    parts = {p for p in key.replace("-", "_").replace(".", "_").replace(" ", "_").split("_") if p}
    if parts & _BLOCKED_PROVIDER_TOKENS:
        return True
    return False


def mock_allowed(env: AppEnvironment) -> bool:
    return env in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}


def _reject(env: AppEnvironment, code: MarketDataGateCode, note: str) -> MarketDataGateResult:
    if code == MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION:
        log.error("Production market data rejected: %s", note)
    else:
        log.warning("Market data gate [%s] env=%s: %s", code.value, env.value, note)
    return MarketDataGateResult(
        ok=False,
        code=code,
        signals_allowed=False,
        note=note,
        environment=env.value,
    )


def _allow(env: AppEnvironment, note: str = "verified") -> MarketDataGateResult:
    return MarketDataGateResult(
        ok=True,
        code=MarketDataGateCode.OK,
        signals_allowed=True,
        note=note,
        environment=env.value,
    )


def gate_provider_selection(provider_name: str, env: AppEnvironment) -> MarketDataGateResult:
    """Call before constructing a provider. Production cannot select mock sources."""
    if mock_allowed(env):
        return _allow(env, f"non-production allows provider={provider_name!r}")
    if is_blocked_provider_name(provider_name):
        return _reject(
            env,
            MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
            f"simulated source name={provider_name!r}",
        )
    return _allow(env, f"provider name permitted: {provider_name!r}")


def gate_provider_instance(provider: Any, env: AppEnvironment) -> MarketDataGateResult:
    """Block simulated/unknown provider instances in production."""
    pid = str(getattr(provider, "provider_id", "") or "")
    kind = getattr(provider, "kind", None)
    if mock_allowed(env):
        return _allow(env, f"non-production provider_id={pid}")

    if is_blocked_provider_name(pid) or is_blocked_provider_name(getattr(provider, "display_name", None)):
        return _reject(
            env,
            MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
            f"simulated source provider_id={pid}",
        )
    if kind in _BLOCKED_KINDS_PRODUCTION:
        return _reject(
            env,
            MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
            f"simulated kind={getattr(kind, 'value', kind)}",
        )
    if kind is None:
        return _reject(
            env,
            MarketDataGateCode.UNKNOWN_SOURCE,
            "unknown source: provider.kind missing",
        )
    if kind not in _VERIFIED_KINDS and kind != DataSourceKind.REQUIRED:
        return _reject(
            env,
            MarketDataGateCode.UNKNOWN_SOURCE,
            f"unknown source kind={getattr(kind, 'value', kind)}",
        )
    return _allow(env, f"provider_id={pid} kind={getattr(kind, 'value', kind)}")


def validate_quote(
    quote: QuoteSnapshot | None,
    *,
    env: AppEnvironment,
    meta: DataSourceMeta | None = None,
    max_age_sec: float = 30.0,
    require_verified_source: bool | None = None,
) -> MarketDataGateResult:
    """Validate a quote before it may drive signals/trading."""
    require_verified = (
        (env == AppEnvironment.PRODUCTION) if require_verified_source is None else require_verified_source
    )

    if quote is None:
        return _reject(env, MarketDataGateCode.NO_MARKET_DATA, "quote is None")

    price = getattr(quote, "price", None)
    if price is None or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "invalid price")

    ts = getattr(quote, "ts", None)
    if ts is None:
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "missing timestamp")

    if isinstance(ts, datetime):
        age = (datetime.now(timezone.utc) - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))).total_seconds()
        if age > max_age_sec:
            return _reject(env, MarketDataGateCode.STALE_DATA, f"stale age={int(age)}s threshold={int(max_age_sec)}s")
    else:
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "timestamp type invalid")

    if meta is not None:
        if meta.freshness == FreshnessStatus.STALE:
            return _reject(env, MarketDataGateCode.STALE_DATA, meta.note)
        if meta.freshness in {FreshnessStatus.NO_DATA, FreshnessStatus.DISCONNECTED}:
            return _reject(env, MarketDataGateCode.NO_MARKET_DATA, meta.note)
        if meta.kind == DataSourceKind.SIMULATED or meta.freshness == FreshnessStatus.FRESH_SIMULATED:
            if require_verified or env == AppEnvironment.PRODUCTION:
                return _reject(
                    env,
                    MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION
                    if env == AppEnvironment.PRODUCTION
                    else MarketDataGateCode.DATA_NOT_VERIFIED,
                    "simulated source",
                )
        if require_verified and not meta.is_live_market:
            return _reject(
                env,
                MarketDataGateCode.DATA_NOT_VERIFIED,
                "DATA NOT VERIFIED — source is not live/broker/delayed fresh feed",
            )
        if meta.kind not in _VERIFIED_KINDS and require_verified:
            if meta.kind in {DataSourceKind.REQUIRED, DataSourceKind.UNAVAILABLE}:
                return _reject(env, MarketDataGateCode.NO_MARKET_DATA, meta.note)
            return _reject(env, MarketDataGateCode.UNKNOWN_SOURCE, f"unknown source kind={meta.kind.value}")

    elif require_verified:
        return _reject(env, MarketDataGateCode.DATA_NOT_VERIFIED, "no source meta")

    return _allow(env, "quote valid")


def validate_bars(bars: list[Bar] | None, *, env: AppEnvironment) -> MarketDataGateResult:
    if not bars:
        return _reject(env, MarketDataGateCode.NO_MARKET_DATA, "empty OHLCV")
    last = bars[-1]
    for attr in ("open", "high", "low", "close"):
        v = getattr(last, attr, None)
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or float(v) <= 0:
            return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, f"invalid OHLCV.{attr}")
    if last.high < last.low:
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "OHLCV high < low")
    if getattr(last, "ts", None) is None:
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "OHLCV missing timestamp")
    return _allow(env, "ohlcv ok")


def gate_market_data_for_scan(
    provider: Any,
    *,
    app_env: str | AppEnvironment,
    max_age_sec: float = 30.0,
) -> MarketDataGateResult:
    """Single entry gate used by TradingService.scan — DATA NOT VERIFIED → NO SIGNAL."""
    env = app_env if isinstance(app_env, AppEnvironment) else normalize_app_env(str(app_env))

    inst = gate_provider_instance(provider, env)
    if not inst.ok:
        return inst

    if not getattr(provider, "has_market_data", lambda: False)():
        return _reject(env, MarketDataGateCode.NO_MARKET_DATA, "provider.has_market_data() is False")

    meta: DataSourceMeta | None = None
    try:
        meta = provider.source_meta(max_age_sec)
    except Exception as exc:  # noqa: BLE001
        return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, f"source_meta failed: {exc}")

    if meta is None:
        return _reject(env, MarketDataGateCode.UNKNOWN_SOURCE, "source meta missing")

    if env == AppEnvironment.PRODUCTION:
        if meta.kind in _BLOCKED_KINDS_PRODUCTION or meta.freshness == FreshnessStatus.FRESH_SIMULATED:
            return _reject(
                env,
                MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
                f"simulated source kind={meta.kind.value}",
            )
        if meta.kind not in _VERIFIED_KINDS:
            if meta.kind in {DataSourceKind.REQUIRED, DataSourceKind.UNAVAILABLE}:
                return _reject(env, MarketDataGateCode.NO_MARKET_DATA, meta.note)
            return _reject(env, MarketDataGateCode.UNKNOWN_SOURCE, f"unknown source kind={meta.kind.value}")
        if not meta.is_live_market:
            if meta.freshness == FreshnessStatus.STALE:
                return _reject(env, MarketDataGateCode.STALE_DATA, meta.note)
            return _reject(env, MarketDataGateCode.DATA_NOT_VERIFIED, meta.note)
        if meta.last_update is None:
            return _reject(env, MarketDataGateCode.INVALID_MARKET_DATA, "missing timestamp")
        if meta.freshness == FreshnessStatus.STALE:
            return _reject(env, MarketDataGateCode.STALE_DATA, meta.note)
    else:
        # Dev/Test: allow simulated; still block empty/stale if no data at all
        if meta.freshness in {FreshnessStatus.NO_DATA, FreshnessStatus.DISCONNECTED}:
            return _reject(env, MarketDataGateCode.NO_MARKET_DATA, meta.note)

    return _allow(env, meta.note)
