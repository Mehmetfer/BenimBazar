"""Heuristic CODER — generate allowlisted writes from a USER GOAL without WriteFn.

Not an LLM. Uses discovery + goal patterns. Unknown goals → EMPTY writes + UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_se.boundaries import assert_se_writes_safe
from agentic_se.find_files import find_files

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CodeProposal:
    writes: dict[str, str]
    test_nodes: list[str]
    rationale: str
    unknown: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "writes": list(self.writes.keys()),
            "test_nodes": self.test_nodes,
            "rationale": self.rationale,
            "unknown": self.unknown,
        }


PROVIDER_RECOVERY_MODULE = '''"""Provider recovery policy — fail-closed SE mirror of trading recovery rules.

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
'''

PROVIDER_RECOVERY_TESTS = '''"""Regression: provider recovery policy remains fail-closed."""

from __future__ import annotations

from agentic_se.provider_recovery_policy import (
    alternate_allowed,
    classify_provider_failure,
)


def test_unknown_order_halts():
    d = classify_provider_failure("UNKNOWN_ORDER after timeout")
    assert d.action == "HALT"


def test_stale_retries():
    d = classify_provider_failure("STALE market data")
    assert d.action == "RETRY"


def test_kill_halts():
    d = classify_provider_failure("KILL_SWITCH active")
    assert d.action == "HALT"


def test_provider_uncertain_needs_validation():
    d = classify_provider_failure("PROVIDER UNAVAILABLE")
    assert d.action == "ALTERNATE_THEN_VALIDATE"
    assert d.may_use_alternate is True


def test_alternate_requires_validation():
    assert alternate_allowed(primary_ok=False, alternate_validated=False) is False
    assert alternate_allowed(primary_ok=False, alternate_validated=True) is True


def test_financial_ambiguity_never_retry():
    for key in ("POSITION_MISMATCH", "BALANCE_MISMATCH", "RECONCILE_FAIL"):
        assert classify_provider_failure(key).action == "HALT"
'''


def propose_code(goal: str, *, root: Path | None = None) -> CodeProposal:
    """Map USER GOAL → allowlisted file writes. Empty + unknown if unsupported."""
    base = root or ROOT
    gl = goal.lower()
    disc = find_files(goal, root=base)

    # Provider recovery improvement (acceptance demo class)
    if any(k in gl for k in ("provider recovery", "provider recover", "recovery sistem", "recovery system")):
        writes = {
            "agentic_se/provider_recovery_policy.py": PROVIDER_RECOVERY_MODULE,
            "tests/test_ase_provider_recovery.py": PROVIDER_RECOVERY_TESTS,
        }
        assert_se_writes_safe(writes)
        return CodeProposal(
            writes=writes,
            test_nodes=["tests/test_ase_provider_recovery.py", "tests/test_ase_smoke.py"],
            rationale=(
                "Discovered autonomous/recovery.py patterns; added fail-closed "
                "provider_recovery_policy + regression tests under allowlist. "
                f"hits={disc.code_hits[:5]}"
            ),
            unknown=False,
        )

    # Memory / orchestrator self-improvement
    if "orchestrator" in gl or "codebase memory" in gl or "agentic_se memory" in gl:
        # Ensure health note file for memory freshness (minimal)
        content = (
            "# Agentic SE memory note\n\n"
            "Memory is regenerated by discovery.discover_repository on each orchestrated goal.\n"
            "Stale entries invalidated via invalidate_memory_for_paths after writes.\n"
        )
        writes = {"agentic_se/data/MEMORY.md": content}
        assert_se_writes_safe(writes)
        return CodeProposal(
            writes=writes,
            test_nodes=["tests/test_ase_smoke.py", "tests/test_orchestrator.py"],
            rationale="Refresh memory documentation for orchestrator",
            unknown=False,
        )

    return CodeProposal(
        writes={},
        test_nodes=["tests/test_ase_smoke.py"],
        rationale="No safe heuristic implementation for this goal — UNKNOWN",
        unknown=True,
    )
