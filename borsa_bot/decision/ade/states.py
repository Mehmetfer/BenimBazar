"""First-class autonomous decision states."""

from __future__ import annotations

from enum import Enum


class DecisionAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


# Actions that may proceed to sizing / execution path (still must pass validators + safety).
EXECUTABLE_ACTIONS = frozenset(
    {
        DecisionAction.BUY,
        DecisionAction.SELL,
        DecisionAction.REDUCE,
        DecisionAction.EXIT,
    }
)

# Soft non-trade outcomes (not failures — intentional abstention).
ABSTAIN_ACTIONS = frozenset(
    {
        DecisionAction.HOLD,
        DecisionAction.WAIT,
        DecisionAction.NO_TRADE,
    }
)


def is_executable(action: DecisionAction | str) -> bool:
    if isinstance(action, DecisionAction):
        return action in EXECUTABLE_ACTIONS
    return DecisionAction(str(action)) in EXECUTABLE_ACTIONS
