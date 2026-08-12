"""SI smoke tests — safe for nested verify during SI iterations (no engine.run)."""

from __future__ import annotations

from self_improvement.invariants import FROZEN_PRODUCTION_INVARIANTS, path_allowed_for_auto_impl
from self_improvement.verify import parse_pytest_summary


def test_smoke_allowlist():
    assert path_allowed_for_auto_impl("self_improvement/baseline_guard.py")
    assert not path_allowed_for_auto_impl("trading_safety/kill_switch.py")


def test_smoke_frozen_invariants():
    assert "kill_switch_no_new_orders" in FROZEN_PRODUCTION_INVARIANTS


def test_smoke_parse_summary():
    assert parse_pytest_summary("3 passed in 0.1s") == (3, 0)
