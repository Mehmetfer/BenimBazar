"""Market type separation — BIST vs CRYPTO.

Kept in crypto package so BIST modules need not import crypto.
Shared layers (validation/provenance/risk) remain market-agnostic.
"""

from __future__ import annotations

from enum import Enum


class MarketType(str, Enum):
    """Application market plane. Default trading path is BIST."""

    BIST = "BIST"
    CRYPTO = "CRYPTO"

    @classmethod
    def parse(cls, raw: object, *, default: "MarketType | None" = None) -> "MarketType":
        if isinstance(raw, MarketType):
            return raw
        if raw is None or str(raw).strip() == "":
            return default if default is not None else cls.BIST
        key = str(raw).strip().upper()
        aliases = {
            "EQUITY": cls.BIST,
            "STOCK": cls.BIST,
            "STOCKS": cls.BIST,
            "HISSE": cls.BIST,
            "PARIBU": cls.CRYPTO,
            "CRYPTOCURRENCY": cls.CRYPTO,
            "COIN": cls.CRYPTO,
        }
        if key in aliases:
            return aliases[key]
        try:
            return cls(key)
        except ValueError:
            return default if default is not None else cls.BIST


def is_crypto_market(raw: object) -> bool:
    return MarketType.parse(raw) == MarketType.CRYPTO
