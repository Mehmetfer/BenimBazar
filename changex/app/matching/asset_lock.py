"""Asset Lock abstraction — settlement NOT implemented in Chain Engine V1.

CHANGE X Chain proposals record consent only. Ownership transfer requires a
future Asset Lock V1. This module exists so callers cannot accidentally invent
ad-hoc settlement paths.
"""

from __future__ import annotations

from typing import Any, Protocol


class AssetLockError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AssetLockProvider(Protocol):
    def lock(self, chain_id: str, listing_ids: list[int]) -> dict[str, Any]: ...

    def unlock(self, chain_id: str) -> dict[str, Any]: ...

    def validate(self, chain_id: str) -> dict[str, Any]: ...

    def commit(self, chain_id: str) -> dict[str, Any]: ...


class NotImplementedAssetLock:
    """Stub provider — always raises NOT_IMPLEMENTED. Never mutates ownership."""

    def lock(self, chain_id: str, listing_ids: list[int]) -> dict[str, Any]:
        raise AssetLockError(
            "ASSET_LOCK_NOT_IMPLEMENTED",
            "Asset Lock settlement is not available in Chain Engine V1",
        )

    def unlock(self, chain_id: str) -> dict[str, Any]:
        raise AssetLockError(
            "ASSET_LOCK_NOT_IMPLEMENTED",
            "Asset Lock settlement is not available in Chain Engine V1",
        )

    def validate(self, chain_id: str) -> dict[str, Any]:
        raise AssetLockError(
            "ASSET_LOCK_NOT_IMPLEMENTED",
            "Asset Lock settlement is not available in Chain Engine V1",
        )

    def commit(self, chain_id: str) -> dict[str, Any]:
        raise AssetLockError(
            "ASSET_LOCK_NOT_IMPLEMENTED",
            "Asset Lock settlement is not available in Chain Engine V1",
        )


_DEFAULT_LOCK: AssetLockProvider = NotImplementedAssetLock()
_LOCK_CALLS: list[tuple[str, str]] = []


def get_asset_lock_provider() -> AssetLockProvider:
    return _DEFAULT_LOCK


def reset_asset_lock_call_log() -> None:
    _LOCK_CALLS.clear()


def asset_lock_call_log() -> list[tuple[str, str]]:
    return list(_LOCK_CALLS)


def guarded_asset_lock_call(method: str, *args: Any, **kwargs: Any) -> None:
    """Record accidental settlement attempts then raise — never transfers ownership."""
    chain_id = str(args[0]) if args else str(kwargs.get("chain_id", ""))
    _LOCK_CALLS.append((method, chain_id))
    getattr(_DEFAULT_LOCK, method)(*args, **kwargs)
