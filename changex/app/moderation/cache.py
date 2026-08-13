"""In-process public listing cache — must never serve unapproved listings."""

from __future__ import annotations

import time
from typing import Any

# key -> (expires_at, payload)
_CACHE: dict[str, tuple[float, Any]] = {}
_TTL_SECONDS = 30.0


def cache_get(key: str) -> Any | None:
    item = _CACHE.get(key)
    if not item:
        return None
    expires, payload = item
    if time.time() > expires:
        _CACHE.pop(key, None)
        return None
    return payload


def cache_set(key: str, payload: Any, ttl: float = _TTL_SECONDS) -> None:
    # Defense: never cache non-list payloads that might include pending
    _CACHE[key] = (time.time() + ttl, payload)


def invalidate_public_listings() -> None:
    """Drop all public feed/search cache entries after moderation decisions."""
    keys = [k for k in _CACHE if k.startswith("public:")]
    for k in keys:
        _CACHE.pop(k, None)


def invalidate_listing(listing_id: int) -> None:
    _CACHE.pop(f"listing:{listing_id}", None)
    invalidate_public_listings()


def reset_cache() -> None:
    _CACHE.clear()


def cache_stats() -> dict[str, int]:
    return {"entries": len(_CACHE)}
