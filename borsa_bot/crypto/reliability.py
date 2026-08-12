"""Crypto MD reliability gate — silent-domain fail-closed for signal emission.

Does not unlock LIVE broker. SIGNAL ≠ EXECUTION.
"""

from __future__ import annotations

from typing import Any

from data.integrity import DataSourceKind


def _kind_of(provider: Any) -> DataSourceKind:
    kind = getattr(provider, "kind", DataSourceKind.UNKNOWN)
    if isinstance(kind, DataSourceKind):
        return kind
    try:
        return DataSourceKind(str(kind))
    except ValueError:
        return DataSourceKind.UNKNOWN


def crypto_signals_permitted(
    provider: Any,
    *,
    crypto_enabled: bool,
    signals_enabled: bool,
    max_age_sec: float = 30.0,
) -> tuple[bool, str]:
    """Return (allowed, reason). Unsafe/unreliable MD → False (fail-closed)."""
    if not crypto_enabled:
        return False, "CRYPTO_ENABLED=false"
    if not signals_enabled:
        return False, "CRYPTO_SIGNALS_ENABLED=false"
    if provider is None:
        return False, "NO_PROVIDER"
    if getattr(provider, "is_stub", False):
        return False, "STUB_PROVIDER"
    if not getattr(provider, "has_market_data", lambda: False)():
        return False, "NO_MARKET_DATA"
    fresh_fn = getattr(provider, "is_fresh", None)
    if callable(fresh_fn) and not bool(fresh_fn(max_age_sec)):
        return False, "STALE_OR_DISCONNECTED"
    kind = _kind_of(provider)
    if kind in {DataSourceKind.SIMULATED, DataSourceKind.TEST, DataSourceKind.UNAVAILABLE, DataSourceKind.UNKNOWN}:
        return False, f"UNRELIABLE_KIND={kind.value}"
    if kind not in {DataSourceKind.LIVE, DataSourceKind.DELAYED}:
        return False, f"NON_LIVE_KIND={kind.value}"
    return True, "OK"
