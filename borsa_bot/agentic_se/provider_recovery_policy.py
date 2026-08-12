"""Provider recovery policy — fail-closed SE mirror of trading recovery rules.

Enhances observability/classification for autonomous coding & ADE alignment.
Does NOT unlock LIVE broker or loosen financial-ambiguity HALT rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Financial ambiguity always HALT (immutable rule for this module).
FINANCIAL_AMBIGUITY = frozenset(
    {
        "UNKNOWN_ORDER",
        "POSITION_MISMATCH",
        "BALANCE_MISMATCH",
        "ORDER_STATUS_UNKNOWN",
        "RECONCILE_FAIL",
    }
)

RETRYABLE = frozenset(
    {
        "STALE",
        "TIMEOUT",
        "DISCONNECT",
        "API_DOWN",
        "NETWORK",
        "PROVIDER_TRANSIENT",
    }
)

HARD_HALT = frozenset(
    {
        "KILL",
        "DAILY_LOSS",
        "DRAWDOWN",
        "MOCK",
        "PRODUCTION",
        "PROVIDER_UNVALIDATED",
    }
)


@dataclass
class RecoveryDecision:
    action: str  # RETRY | HALT | ALTERNATE_THEN_VALIDATE
    reason: str
    may_use_alternate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_provider_failure(reason: str) -> RecoveryDecision:
    """Classify provider/trading failure for recovery.

    Financial ambiguity → HALT (never RETRY into duplicate-order risk).
    Transient provider issues → RETRY.
    Unvalidated alternate → HALT (caller must validate before ALTERNATE).
    """
    r = (reason or "").upper()
    for key in FINANCIAL_AMBIGUITY:
        if key in r:
            return RecoveryDecision("HALT", f"financial_ambiguity:{key}", False)
    for key in HARD_HALT:
        if key in r:
            return RecoveryDecision("HALT", f"hard_halt:{key}", False)
    for key in RETRYABLE:
        if key in r:
            return RecoveryDecision("RETRY", f"transient:{key}", True)
    if "PROVIDER" in r and ("UNKNOWN" in r or "UNAVAILABLE" in r or "UNCERTAIN" in r):
        # May attempt alternate only after explicit validation by caller.
        return RecoveryDecision("ALTERNATE_THEN_VALIDATE", "provider_uncertain", True)
    return RecoveryDecision("HALT", "unknown_failure_fail_closed", False)


def alternate_allowed(*, primary_ok: bool, alternate_validated: bool) -> bool:
    """Alternate provider usable only when validated; else fail-closed."""
    if primary_ok:
        return False
    return bool(alternate_validated)
