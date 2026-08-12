"""Production safety invariants — self-improvement MUST NOT auto-mutate these."""

from __future__ import annotations

from typing import FrozenSet


class SafetyViolation(RuntimeError):
    """Raised when SI attempts to weaken or bypass a frozen invariant."""


# Paths SI may auto-modify (relative to borsa_bot/). Trading-critical cores excluded.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "self_improvement/",
    "autonomy/lessons/",
    "autonomy/evidence/",
    "autonomy/reports/",
    "docs/",
    "tests/test_self_improvement",
)

# Paths SI must never auto-modify in production loops.
DENYLIST_PREFIXES: tuple[str, ...] = (
    "risk/",
    "trading_safety/kill_switch",
    "trading_safety/order_gate",
    "execution/broker",
    "config/settings.py",
    ".env",
    "credentials",
)

FROZEN_PRODUCTION_INVARIANTS: FrozenSet[str] = frozenset(
    {
        "unknown_provider_state_blocks",
        "unknown_broker_state_blocks",
        "unknown_order_state_reconcile",
        "stale_market_data_blocks",
        "risk_calculation_failure_blocks",
        "audit_failure_blocks",
        "duplicate_order_suspicion_blocks",
        "kill_switch_no_new_orders",
        "live_broker_default_locked",
        "no_test_deletion",
        "no_audit_deletion",
        "no_safety_gate_bypass",
        "no_risk_hard_limit_loosening",
        "no_credential_mutation",
    }
)

# File path fragments that imply CRITICAL change-risk when touched.
HIGH_RISK_PATH_MARKERS: tuple[str, ...] = (
    "risk/",
    "trading_safety/",
    "execution/",
    "broker",
    "auth",
    "kill_switch",
    "order_gate",
    "settings.py",
    "ledger",
)


def path_allowed_for_auto_impl(rel_path: str) -> bool:
    p = rel_path.replace("\\", "/").lstrip("./")
    if p.startswith("borsa_bot/"):
        p = p[len("borsa_bot/") :]
    for d in DENYLIST_PREFIXES:
        if p.startswith(d) or d in p:
            return False
    return any(p.startswith(a) for a in ALLOWLIST_PREFIXES)


def assert_invariant_untouched(proposed_changes: dict[str, str]) -> None:
    """Reject proposals that try to disable frozen invariant markers in deny paths."""
    forbidden_patterns = (
        "kill_switch_active=False",
        "live_broker_enabled=True",
        "fail_closed=False",
        "SAFETY_GATE_BYPASS",
        "DELETE FROM audit",
    )
    for path, content in proposed_changes.items():
        if not path_allowed_for_auto_impl(path):
            raise SafetyViolation(f"path not allowlisted for auto-impl: {path}")
        for pat in forbidden_patterns:
            if pat in content:
                raise SafetyViolation(f"forbidden pattern {pat!r} in {path}")
