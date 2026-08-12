"""Human / safety boundaries for the SE agent (trading invariants untouched)."""

from __future__ import annotations

from typing import FrozenSet

from self_improvement.invariants import (
    FROZEN_PRODUCTION_INVARIANTS,
    SafetyViolation,
    path_allowed_for_auto_impl,
)

# SE agent may also touch agentic_se/ and its tests.
SE_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "agentic_se/",
    "self_improvement/",
    "autonomy/lessons/",
    "autonomy/evidence/",
    "autonomy/reports/",
    "docs/",
    "tests/test_agentic_se",
    "tests/test_si_smoke",
    "tests/test_self_improvement",
    "tests/test_ase_",
)

FORBIDDEN_ACTIONS: FrozenSet[str] = frozenset(
    {
        "delete_tests",
        "weaken_assertion_to_pass",
        "bypass_safety_gate",
        "unlock_live_broker",
        "loosen_risk_limits",
        "remove_kill_switch",
        "delete_audit",
        "mutate_credentials",
    }
)


def se_path_allowed(rel_path: str) -> bool:
    p = rel_path.replace("\\", "/").lstrip("./")
    if p.startswith("borsa_bot/"):
        p = p[len("borsa_bot/") :]
    if any(p.startswith(a) for a in SE_ALLOWLIST_PREFIXES):
        return True
    return path_allowed_for_auto_impl(p)


def assert_se_writes_safe(writes: dict[str, str]) -> None:
    for path, content in writes.items():
        if not se_path_allowed(path):
            raise SafetyViolation(f"SE agent path not allowed: {path}")
        low = content.lower()
        if "live_broker_enabled=true" in low.replace(" ", ""):
            raise SafetyViolation("cannot unlock live broker")
        if "kill_switch_active=false" in low.replace(" ", ""):
            raise SafetyViolation("cannot clear kill switch")
        if "safety_gate_bypass" in low:
            raise SafetyViolation("cannot bypass safety gate")


__all__ = [
    "FORBIDDEN_ACTIONS",
    "FROZEN_PRODUCTION_INVARIANTS",
    "SafetyViolation",
    "assert_se_writes_safe",
    "se_path_allowed",
]
