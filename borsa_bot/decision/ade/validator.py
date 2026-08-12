"""Decision + risk validators — second-look before safety gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.reasons import (
    RC_DATA_STALE,
    RC_RISK_REWARD_POOR,
    RC_RISK_VALIDATION_FAILED,
    RC_SIGNAL_CONFLICT,
    RC_SIZE_CAPPED_TO_ZERO,
    RC_VALIDATION_FAILED,
    DecisionReason,
)
from decision.ade.states import DecisionAction, is_executable


@dataclass
class ValidationResult:
    ok: bool
    reason: DecisionReason
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason.to_dict(), "checks": self.checks}


def validate_decision(
    *,
    action: DecisionAction,
    data_fresh: bool,
    data_valid: bool,
    signal_consistent: bool,
    signals: list[str],
    calculated_size: float,
    capped_size: float,
    limits: ImmutableSafetyLimits,
    expected_execution_ok: bool,
    decision_confidence: float,
) -> ValidationResult:
    """Pre-execution decision validator. Inconsistency → block (no order)."""
    reason = DecisionReason(stage="DECISION_VALIDATOR")
    checks: list[str] = []

    if not data_valid:
        reason.add(RC_VALIDATION_FAILED, "data invalid")
        checks.append("data_valid=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("data_valid")

    if not data_fresh:
        reason.add(RC_DATA_STALE, "stale data")
        checks.append("data_fresh=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("data_fresh")

    if is_executable(action) and not signal_consistent:
        reason.add(RC_SIGNAL_CONFLICT, "signals inconsistent for executable action", signals=signals)
        checks.append("signal_consistent=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("signal_consistent")

    if is_executable(action) and capped_size <= 0:
        reason.add(RC_SIZE_CAPPED_TO_ZERO, "executable action but size is zero")
        checks.append("size=FAIL")
        return ValidationResult(False, reason, checks)

    if capped_size > limits.hard_max_position_size + 1e-9:
        reason.add(RC_VALIDATION_FAILED, "capped size exceeds hard max — invariant broken")
        checks.append("hard_max=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("hard_max")

    if calculated_size + 1e-9 < capped_size:
        # capped must never exceed calculated upward
        reason.add(RC_VALIDATION_FAILED, "capped_size > calculated_size")
        checks.append("size_monotonic=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("size_monotonic")

    if is_executable(action) and decision_confidence < limits.confidence_threshold:
        reason.add(RC_VALIDATION_FAILED, "confidence below threshold at validator")
        checks.append("confidence=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("confidence")

    if is_executable(action) and not expected_execution_ok:
        reason.add(RC_VALIDATION_FAILED, "expected execution not ok")
        checks.append("expected_execution=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("expected_execution")

    reason.add("DECISION_VALIDATOR_OK", "decision inputs consistent")
    return ValidationResult(True, reason, checks)


def validate_risk(
    *,
    action: DecisionAction,
    daily_loss_pct: float,
    exposure_pct: float,
    risk_reward: float | None,
    expected_value: float | None,
    slippage_bps: float,
    limits: ImmutableSafetyLimits,
    kill_switch: bool,
) -> ValidationResult:
    reason = DecisionReason(stage="RISK_VALIDATOR")
    checks: list[str] = []

    if kill_switch or limits.kill_switch_active:
        reason.add(RC_RISK_VALIDATION_FAILED, "kill switch active")
        checks.append("kill_switch=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("kill_switch")

    if daily_loss_pct >= limits.hard_max_daily_loss_pct:
        reason.add(RC_RISK_VALIDATION_FAILED, "daily loss limit", daily_loss_pct=daily_loss_pct)
        checks.append("daily_loss=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("daily_loss")

    if exposure_pct > limits.hard_max_exposure_pct:
        reason.add(RC_RISK_VALIDATION_FAILED, "exposure limit", exposure_pct=exposure_pct)
        checks.append("exposure=FAIL")
        return ValidationResult(False, reason, checks)
    checks.append("exposure")

    if is_executable(action):
        if expected_value is not None and expected_value < limits.min_expected_value:
            reason.add(RC_RISK_VALIDATION_FAILED, "EV below min", expected_value=expected_value)
            checks.append("ev=FAIL")
            return ValidationResult(False, reason, checks)
        checks.append("ev")

        if risk_reward is not None and risk_reward < 1.0 and action in {DecisionAction.BUY, DecisionAction.SELL}:
            reason.add(RC_RISK_REWARD_POOR, "RR < 1", risk_reward=risk_reward)
            checks.append("rr=FAIL")
            return ValidationResult(False, reason, checks)
        checks.append("rr")

        if slippage_bps > limits.max_slippage_bps:
            reason.add(RC_RISK_VALIDATION_FAILED, "slippage too high", slippage_bps=slippage_bps)
            checks.append("slippage=FAIL")
            return ValidationResult(False, reason, checks)
        checks.append("slippage")

    reason.add("RISK_VALIDATOR_OK", "risk checks passed")
    return ValidationResult(True, reason, checks)
