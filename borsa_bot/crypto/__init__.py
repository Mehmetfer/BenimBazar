"""CRYPTO market foundation — isolated from BIST trading path.

Phase 1: architecture only. No Paribu HTTP, no live crypto trading.
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
