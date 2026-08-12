"""Autonomous Decision Engine (ADE) — humanless decisions within immutable safety limits."""

from __future__ import annotations

from decision.ade.chain import CHAIN_ORDER, ChainResult, MarketSnapshot, run_decision_chain
from decision.ade.confidence import compute_decision_confidence
from decision.ade.correction import FailureClass, run_self_correction
from decision.ade.engine import AutonomousDecisionEngine, AutonomousDecisionRecord
from decision.ade.learning import AdaptiveLearner
from decision.ade.limits import AdaptiveState, ImmutableSafetyLimits, SafetyBypassError
from decision.ade.loop import AutonomousTradingLoop
from decision.ade.scorecard import DecisionAutonomyScorecard, score_decision_autonomy
from decision.ade.sizing import calculate_position_size
from decision.ade.states import DecisionAction
from decision.ade.validator import validate_decision, validate_risk

__all__ = [
    "AdaptiveLearner",
    "AdaptiveState",
    "AutonomousDecisionEngine",
    "AutonomousDecisionRecord",
    "AutonomousTradingLoop",
    "CHAIN_ORDER",
    "ChainResult",
    "DecisionAction",
    "DecisionAutonomyScorecard",
    "FailureClass",
    "ImmutableSafetyLimits",
    "MarketSnapshot",
    "SafetyBypassError",
    "calculate_position_size",
    "compute_decision_confidence",
    "run_decision_chain",
    "run_self_correction",
    "score_decision_autonomy",
    "validate_decision",
    "validate_risk",
]
