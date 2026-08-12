"""Stop conditions for the SI maintenance loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StopDecision:
    stop: bool
    reason: str
    kind: str = "CONTINUE"  # SAFE_STOP | CONTINUE
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_stop(
    *,
    critical_regression: bool = False,
    security_regression: bool = False,
    test_instability: bool = False,
    uncertain_behavior: bool = False,
    data_corruption_risk: bool = False,
    unsafe_trading_behavior: bool = False,
    repeated_failed_attempts: int = 0,
    no_measurable_improvement: bool = False,
    max_iterations_reached: bool = False,
    backlog_empty: bool = False,
) -> StopDecision:
    signals: list[str] = []
    if critical_regression:
        signals.append("critical_regression")
    if security_regression:
        signals.append("security_regression")
    if test_instability:
        signals.append("test_instability")
    if uncertain_behavior:
        signals.append("uncertain_behavior")
    if data_corruption_risk:
        signals.append("data_corruption_risk")
    if unsafe_trading_behavior:
        signals.append("unsafe_trading_behavior")
    if repeated_failed_attempts >= 3:
        signals.append("repeated_failed_attempts")
    if no_measurable_improvement:
        signals.append("no_measurable_improvement")
    if max_iterations_reached:
        signals.append("max_iterations_reached")
    if backlog_empty:
        signals.append("backlog_empty")

    hard = {
        "critical_regression",
        "security_regression",
        "data_corruption_risk",
        "unsafe_trading_behavior",
        "repeated_failed_attempts",
    }
    if hard.intersection(signals) or max_iterations_reached or backlog_empty:
        reason = ", ".join(signals) if signals else "safe_stop"
        return StopDecision(True, reason=reason, kind="SAFE_STOP", signals=signals)
    if no_measurable_improvement or test_instability or uncertain_behavior:
        return StopDecision(True, reason=", ".join(signals), kind="SAFE_STOP", signals=signals)
    return StopDecision(False, reason="continue", kind="CONTINUE", signals=signals)
