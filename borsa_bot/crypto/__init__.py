"""CRYPTO market foundation — isolated from BIST trading path.

Phase 1–4: market type, Paribu MD, analytics/signals, dashboard UI (paper only).
Default: CRYPTO_ENABLED=false → BIST behavior unchanged.
"""

from crypto.market import MarketType
from crypto.providers.factory import create_crypto_provider
from crypto.service import CryptoFoundationService

__all__ = [
    "MarketType",
    "create_crypto_provider",
    "CryptoFoundationService",
]
