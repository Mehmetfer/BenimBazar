"""Production trading safety layer — fail-closed, paper/shadow/micro-live.

Does NOT unlock LIVE broker or send real-money orders by default.
Engineering autonomy (8.45) is separate from trading safety / live-money readiness.
"""

from __future__ import annotations

from trading_safety.modes import TradingExecutionMode, parse_trading_mode
from trading_safety.pipeline import SafeExecutionPipeline, SafeSubmitResult
from trading_safety.scorecard import TradingAutonomyScorecard, score_trading_autonomy

__all__ = [
    "SafeExecutionPipeline",
    "SafeSubmitResult",
    "TradingAutonomyScorecard",
    "TradingExecutionMode",
    "parse_trading_mode",
    "score_trading_autonomy",
]
