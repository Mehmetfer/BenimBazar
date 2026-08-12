"""Regression: provider recovery policy remains fail-closed."""

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
