"""CHANGE X matching / Chain Engine configuration."""

from __future__ import annotations

import os

# Production default: Chain algorithm OFF.
CHANGE_CHAIN_ENABLED = os.environ.get("CHANGE_CHAIN_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}

# Max cycle length (nodes). Production default 4 (supports 3- and 4-cycles).
CHANGE_CHAIN_MAX_LENGTH = int(os.environ.get("CHANGE_CHAIN_MAX_LENGTH", "4"))
# Minimum meaningful chain (A→B→C→A); 2-node mutual is not a Chain.
CHANGE_CHAIN_MIN_LENGTH = 3

# Proposal TTL seconds (default 24h)
CHANGE_CHAIN_PROPOSAL_TTL_SECONDS = int(
    os.environ.get("CHANGE_CHAIN_PROPOSAL_TTL_SECONDS", str(86_400))
)

COMPATIBILITY_POLICY_VERSION = "CHANGE_X_CATEGORY_COMPAT_V1"
MATCHING_POLICY_VERSION = "CHANGE_X_MATCHING_CONTRACT_V1"
CHAIN_ENGINE_VERSION = "CHANGE_CHAIN_ENGINE_V1"

# Known marketplace categories (from Flutter shell / API usage)
KNOWN_CATEGORIES = (
    "Elektronik",
    "Spor",
    "Ev",
    "Kitap",
    "Moda",
    "Diğer",
    "Otomobil",
    "Telefon",
    "Bilgisayar",
)


def change_chain_enabled() -> bool:
    """Read flag from module attribute (tests may monkeypatch)."""
    return bool(CHANGE_CHAIN_ENABLED)


def chain_max_length() -> int:
    return max(CHANGE_CHAIN_MIN_LENGTH, int(CHANGE_CHAIN_MAX_LENGTH))
