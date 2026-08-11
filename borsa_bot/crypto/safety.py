"""Crypto production safety — fail closed. Never feed mock crypto into PRODUCTION trades.

Isolated from BIST validation.py so BIST gates stay untouched.
Reuses AppEnvironment + gate codes where useful.
"""

from __future__ import annotations

from typing import Any

from crypto.market import MarketType
from data.integrity import DataSourceKind
from data.validation import AppEnvironment, MarketDataGateCode, MarketDataGateResult, normalize_app_env


_MOCK_CRYPTO_TOKENS = frozenset(
    {
        "simulated",
        "sim",
        "mock",
        "demo",
        "fake",
        "synthetic",
        "dummy",
        "placeholder",
        "random",
        "test",
    }
)


def is_mock_crypto_provider_name(name: str | None) -> bool:
    key = (name or "").strip().lower()
    if not key:
        return False
    if key in _MOCK_CRYPTO_TOKENS:
        return True
    parts = {p for p in key.replace("-", "_").split("_") if p}
    return bool(parts & _MOCK_CRYPTO_TOKENS)


def _gate(
    *,
    ok: bool,
    code: MarketDataGateCode,
    note: str,
    env: AppEnvironment,
    signals_allowed: bool = False,
) -> MarketDataGateResult:
    return MarketDataGateResult(
        ok=ok,
        code=code,
        signals_allowed=signals_allowed,
        note=note,
        environment=env.value,
    )


def gate_crypto_enabled(enabled: bool, *, app_env: str | AppEnvironment) -> MarketDataGateResult:
    env = app_env if isinstance(app_env, AppEnvironment) else normalize_app_env(str(app_env))
    if not enabled:
        return _gate(
            ok=False,
            code=MarketDataGateCode.NO_MARKET_DATA,
            note="CRYPTO_ENABLED=false — crypto market disabled (BIST unaffected)",
            env=env,
            signals_allowed=False,
        )
    # Enabled flag only — still not tradeable until real feed + strategy (Phase 2+)
    return _gate(
        ok=True,
        code=MarketDataGateCode.OK,
        note="crypto enabled (signals still gated by provider)",
        env=env,
        signals_allowed=False,
    )


def gate_crypto_provider(
    provider: Any,
    *,
    app_env: str | AppEnvironment,
    crypto_enabled: bool,
) -> MarketDataGateResult:
    """NO DATA → NO SIGNAL → NO TRADE for crypto plane."""
    env = app_env if isinstance(app_env, AppEnvironment) else normalize_app_env(str(app_env))

    if not crypto_enabled:
        return _gate(
            ok=False,
            code=MarketDataGateCode.NO_MARKET_DATA,
            note="CRYPTO_ENABLED=false",
            env=env,
        )

    if getattr(provider, "is_stub", False):
        return _gate(
            ok=False,
            code=MarketDataGateCode.STUB_NOT_IMPLEMENTED,
            note="Paribu stub — NO MARKET DATA — NO CRYPTO TRADE",
            env=env,
        )

    # Trigger refresh if provider supports tick
    try:
        tick = getattr(provider, "tick", None)
        if callable(tick):
            tick()
    except Exception as exc:  # noqa: BLE001
        return _gate(
            ok=False,
            code=MarketDataGateCode.NO_MARKET_DATA,
            note=f"PROVIDER_FAILURE: {exc}",
            env=env,
        )

    if not getattr(provider, "has_market_data", lambda: False)():
        return _gate(
            ok=False,
            code=MarketDataGateCode.NO_MARKET_DATA,
            note="crypto provider has_market_data() is False",
            env=env,
        )

    kind = getattr(provider, "kind", DataSourceKind.UNKNOWN)
    if isinstance(kind, DataSourceKind):
        kind_v = kind
    else:
        try:
            kind_v = DataSourceKind(str(kind))
        except ValueError:
            kind_v = DataSourceKind.UNKNOWN

    if kind_v in {DataSourceKind.SIMULATED, DataSourceKind.TEST} or (
        env == AppEnvironment.PRODUCTION and kind_v == DataSourceKind.UNKNOWN
    ):
        return _gate(
            ok=False,
            code=MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
            note=f"rejects mock/unknown crypto source kind={kind_v.value}",
            env=env,
        )

    meta = None
    try:
        meta = provider.source_meta()
    except Exception:  # noqa: BLE001
        meta = None
    if meta is not None:
        from data.integrity import FreshnessStatus

        if getattr(meta, "freshness", None) == FreshnessStatus.STALE:
            return _gate(
                ok=False,
                code=MarketDataGateCode.STALE_DATA,
                note=getattr(meta, "note", "stale crypto data"),
                env=env,
            )

    # Live MD OK for observation; signals only when CRYPTO_SIGNALS_ENABLED
    from config.settings import settings as _settings

    signals_ok = bool(getattr(_settings, "crypto_signals_enabled", False))
    return _gate(
        ok=True,
        code=MarketDataGateCode.OK,
        note=(
            "crypto LIVE market data — signals enabled (paper only)"
            if signals_ok
            else "crypto LIVE market data available — signals disabled (CRYPTO_SIGNALS_ENABLED=false)"
        ),
        env=env,
        signals_allowed=signals_ok,
    )


def crypto_provenance_fields(
    *,
    provider_id: str = "paribu",
    data_source_kind: str | DataSourceKind = DataSourceKind.REQUIRED,
) -> dict[str, str]:
    """Provenance stamp for crypto records — never label as BIST."""
    kind = data_source_kind.value if isinstance(data_source_kind, DataSourceKind) else str(data_source_kind)
    return {
        "market_type": MarketType.CRYPTO.value,
        "data_source_kind": kind,
        "provider": provider_id,
    }
