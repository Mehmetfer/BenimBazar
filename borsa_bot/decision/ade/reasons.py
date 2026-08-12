"""Machine-readable reason codes for autonomous decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# --- NO_TRADE / abstain codes ---
RC_LOW_CONFIDENCE = "LOW_CONFIDENCE"
RC_SIGNAL_CONFLICT = "SIGNAL_CONFLICT"
RC_DATA_STALE = "DATA_STALE"
RC_DATA_INVALID = "DATA_INVALID"
RC_PROVIDER_UNCERTAIN = "PROVIDER_UNCERTAIN"
RC_EV_INSUFFICIENT = "EXPECTED_VALUE_INSUFFICIENT"
RC_RISK_REWARD_POOR = "RISK_REWARD_POOR"
RC_SLIPPAGE_HIGH = "SLIPPAGE_HIGH"
RC_REGIME_UNCERTAIN = "REGIME_UNCERTAIN"
RC_EXPOSURE_HIGH = "PORTFOLIO_EXPOSURE_HIGH"
RC_VALIDATION_FAILED = "DECISION_VALIDATION_FAILED"
RC_RISK_VALIDATION_FAILED = "RISK_VALIDATION_FAILED"
RC_SAFETY_GATE_BLOCKED = "SAFETY_GATE_BLOCKED"
RC_SIZE_CAPPED_TO_ZERO = "SIZE_CAPPED_TO_ZERO"
RC_KILL_SWITCH = "KILL_SWITCH"
RC_RECOVERY_FAILED = "RECOVERY_FAILED"
RC_UNKNOWN_STATE = "UNKNOWN_STATE"
RC_HUMAN_WAIT_FORBIDDEN = "HUMAN_WAIT_FORBIDDEN"

# --- affirmative / support codes ---
RC_MULTI_SIGNAL_OK = "MULTI_SIGNAL_CONFIRMED"
RC_REGIME_SUPPORT = "REGIME_SUPPORT"
RC_EV_POSITIVE = "EXPECTED_VALUE_POSITIVE"
RC_SIZE_WITHIN_HARD_MAX = "SIZE_WITHIN_HARD_MAX"
RC_VALIDATORS_PASSED = "VALIDATORS_PASSED"
RC_SAFETY_PASSED = "SAFETY_GATE_PASSED"
RC_POST_TRADE_OK = "POST_TRADE_VERIFIED"


@dataclass
class DecisionReason:
    """Machine-readable justification for a decision."""

    codes: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    stage: str = ""

    def add(self, code: str, message: str = "", **inputs: Any) -> None:
        if code not in self.codes:
            self.codes.append(code)
        if message:
            self.messages.append(message)
        if inputs:
            self.inputs.update(inputs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
