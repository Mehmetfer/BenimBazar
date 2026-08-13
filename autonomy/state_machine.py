"""Autonomy state machine with validated transitions (no OBSERVING→DEPLOYED)."""

from __future__ import annotations

from enum import Enum


class AutonomyState(str, Enum):
    OBSERVING = "OBSERVING"
    DETECTED = "DETECTED"
    DIAGNOSING = "DIAGNOSING"
    PLANNING = "PLANNING"
    PROPOSED = "PROPOSED"
    SANDBOXING = "SANDBOXING"
    TESTING = "TESTING"
    VERIFYING = "VERIFYING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    LEARNED = "LEARNED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PAUSED_FOR_REVIEW = "PAUSED_FOR_REVIEW"
    ABORTED = "ABORTED"


# Explicit allow-list — dangerous jumps (e.g. OBSERVING → DEPLOYED) impossible
ALLOWED: dict[AutonomyState, set[AutonomyState]] = {
    AutonomyState.OBSERVING: {AutonomyState.DETECTED, AutonomyState.PAUSED_FOR_REVIEW, AutonomyState.ABORTED},
    AutonomyState.DETECTED: {AutonomyState.DIAGNOSING, AutonomyState.LEARNED, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.DIAGNOSING: {AutonomyState.PLANNING, AutonomyState.FAILED, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.PLANNING: {AutonomyState.PROPOSED, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.PROPOSED: {AutonomyState.SANDBOXING, AutonomyState.READY_FOR_REVIEW, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.SANDBOXING: {AutonomyState.TESTING, AutonomyState.FAILED, AutonomyState.ROLLING_BACK},
    AutonomyState.TESTING: {AutonomyState.VERIFYING, AutonomyState.FAILED, AutonomyState.ROLLING_BACK},
    AutonomyState.VERIFYING: {
        AutonomyState.PASSED,
        AutonomyState.FAILED,
        AutonomyState.ROLLING_BACK,
        AutonomyState.READY_FOR_REVIEW,
    },
    AutonomyState.PASSED: {AutonomyState.READY_FOR_REVIEW, AutonomyState.LEARNED},
    AutonomyState.FAILED: {AutonomyState.ROLLING_BACK, AutonomyState.LEARNED, AutonomyState.ABORTED},
    AutonomyState.ROLLING_BACK: {AutonomyState.LEARNED, AutonomyState.ABORTED, AutonomyState.FAILED},
    AutonomyState.LEARNED: {AutonomyState.OBSERVING, AutonomyState.READY_FOR_REVIEW, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.READY_FOR_REVIEW: {AutonomyState.OBSERVING, AutonomyState.PAUSED_FOR_REVIEW},
    AutonomyState.PAUSED_FOR_REVIEW: {AutonomyState.OBSERVING, AutonomyState.ABORTED},
    AutonomyState.ABORTED: set(),
}


class InvalidTransition(Exception):
    def __init__(self, src: AutonomyState, dst: AutonomyState) -> None:
        super().__init__(f"illegal transition {src.value} → {dst.value}")
        self.src = src
        self.dst = dst


class AutonomyStateMachine:
    def __init__(self, initial: AutonomyState = AutonomyState.OBSERVING) -> None:
        self.state = initial
        self.history: list[str] = [initial.value]

    def can(self, dst: AutonomyState) -> bool:
        return dst in ALLOWED.get(self.state, set())

    def transition(self, dst: AutonomyState) -> AutonomyState:
        if not self.can(dst):
            raise InvalidTransition(self.state, dst)
        self.state = dst
        self.history.append(dst.value)
        return self.state
