"""Market-data cache with source + freshness — stale cache is NOT TRADEABLE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from data.contract import DataQuality
from data.integrity import DataSourceKind
from data.provenance import parse_data_source_kind, tradeable_flag

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    provider: str
    data_source_kind: str
    timestamp: datetime  # data timestamp (UTC-aware)
    received_at: datetime
    ttl_sec: float

    @property
    def age_seconds(self) -> float:
        ts = self.timestamp
        if ts.tzinfo is None:
            return 1e9
        return max(0.0, (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds())

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds <= self.ttl_sec

    @property
    def quality(self) -> DataQuality:
        if self.timestamp.tzinfo is None:
            return DataQuality.INVALID
        if not self.is_fresh:
            return DataQuality.STALE
        kind = parse_data_source_kind(self.data_source_kind)
        if kind == DataSourceKind.UNKNOWN:
            return DataQuality.UNKNOWN_SOURCE
        return DataQuality.VALID

    @property
    def tradeable(self) -> bool:
        if self.quality != DataQuality.VALID:
            return False
        return tradeable_flag(self.data_source_kind, verified=True)

    def to_meta(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "data_source_kind": self.data_source_kind,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "received_at": self.received_at.isoformat(),
            "ttl_sec": self.ttl_sec,
            "age_seconds": round(self.age_seconds, 1),
            "freshness": "FRESH" if self.is_fresh else "STALE",
            "quality": self.quality.value,
            "tradeable": self.tradeable,
        }


class MarketDataCache:
    """Keyed cache. Provider down + stale entry → NOT TRADEABLE (no live relabel)."""

    def __init__(self, default_ttl_sec: float = 30.0) -> None:
        self.default_ttl_sec = default_ttl_sec
        self._entries: dict[str, CacheEntry[Any]] = {}

    def put(
        self,
        key: str,
        value: Any,
        *,
        provider: str,
        data_source_kind: str,
        timestamp: datetime,
        ttl_sec: float | None = None,
    ) -> CacheEntry[Any]:
        entry = CacheEntry(
            value=value,
            provider=provider,
            data_source_kind=data_source_kind,
            timestamp=timestamp,
            received_at=datetime.now(timezone.utc),
            ttl_sec=float(ttl_sec if ttl_sec is not None else self.default_ttl_sec),
        )
        self._entries[key] = entry
        return entry

    def get(self, key: str) -> CacheEntry[Any] | None:
        return self._entries.get(key)

    def get_fresh(self, key: str) -> CacheEntry[Any] | None:
        e = self.get(key)
        if e is None or not e.is_fresh:
            return None
        return e

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._entries.clear()
        else:
            self._entries.pop(key, None)

    def tradeable_or_none(self, key: str) -> Any | None:
        e = self.get(key)
        if e is None or not e.tradeable:
            return None
        return e.value
