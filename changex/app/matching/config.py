"""Exchange Graph V1 — matching infrastructure (no Change Chain algorithm)."""

from __future__ import annotations

import os

# Production default: Chain algorithm OFF. Data model may still be prepared.
CHANGE_CHAIN_ENABLED = os.environ.get("CHANGE_CHAIN_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}

COMPATIBILITY_POLICY_VERSION = "CHANGE_X_CATEGORY_COMPAT_V1"
MATCHING_POLICY_VERSION = "CHANGE_X_MATCHING_CONTRACT_V1"

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
