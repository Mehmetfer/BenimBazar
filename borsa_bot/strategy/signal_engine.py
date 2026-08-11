"""Compatibility exports for strategy.signal_engine."""
from signals.engine import (
    build_explanation,
    decide_action,
    score_buy,
    score_sell,
)

__all__ = ["build_explanation", "decide_action", "score_buy", "score_sell"]
