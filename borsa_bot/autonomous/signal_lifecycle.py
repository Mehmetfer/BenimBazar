"""Signal lifecycle — expiration & invalidation (Master V2 §22–23)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from config.models import utc_now
from config.settings import settings


@dataclass
class SignalLifecycle:
    symbol: str
    signal: str
    created_at: str
    expires_at: str
    valid: bool = True
    invalidation_reason: str | None = None
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_lifecycle(
    symbol: str,
    signal: str,
    *,
    created: datetime | None = None,
    ttl_sec: float | None = None,
) -> SignalLifecycle:
    created = created or utc_now()
    ttl = float(ttl_sec if ttl_sec is not None else getattr(settings, "signal_ttl_sec", 3600))
    exp = created + timedelta(seconds=ttl)
    return SignalLifecycle(
        symbol=symbol.upper(),
        signal=signal,
        created_at=created.isoformat(),
        expires_at=exp.isoformat(),
        valid=True,
    )


def is_expired(life: SignalLifecycle, *, now: datetime | None = None) -> bool:
    now = now or utc_now()
    try:
        exp = datetime.fromisoformat(life.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return now >= exp


def invalidate(life: SignalLifecycle, reason: str, *codes: str) -> SignalLifecycle:
    life.valid = False
    life.invalidation_reason = reason
    life.reason_codes = list(codes) or [reason]
    return life


def evaluate_invalidation(
    life: SignalLifecycle,
    *,
    data_stale: bool = False,
    regime_changed: bool = False,
    mtf_conflict: bool = False,
    spread_expanded: bool = False,
    risk_changed: bool = False,
    price_moved_too_far: bool = False,
) -> SignalLifecycle:
    if is_expired(life):
        return invalidate(life, "SIGNAL_EXPIRED", "SIGNAL_EXPIRED")
    if data_stale:
        return invalidate(life, "DATA_STALE", "DATA_STALE")
    if regime_changed:
        return invalidate(life, "REGIME_CHANGED", "REGIME_CONFLICT")
    if mtf_conflict:
        return invalidate(life, "TIMEFRAME_CONFLICT", "MTF_CONFLICT")
    if spread_expanded:
        return invalidate(life, "SPREAD_EXPANDED", "DATA_ANOMALY")
    if risk_changed:
        return invalidate(life, "RISK_CHANGED", "RISK_REJECTED")
    if price_moved_too_far:
        return invalidate(life, "PRICE_MOVED_TOO_FAR", "SIGNAL_INVALIDATED")
    return life
