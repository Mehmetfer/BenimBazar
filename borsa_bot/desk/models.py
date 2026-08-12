"""Structured models for institutional desk decisions — no invented market data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class StageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class DeskSessionMode(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    INTRADAY = "INTRADAY"
    POST_MARKET = "POST_MARKET"


class AnalystRole(str, Enum):
    MARKET = "market_analyst"
    QUANT = "quant_analyst"
    TECHNICAL = "technical_analyst"
    FUNDAMENTAL = "fundamental_analyst"
    REGIME = "regime_analyst"
    RISK = "risk_manager"
    PORTFOLIO = "portfolio_manager"
    EXECUTION = "execution_manager"


@dataclass
class AnalystVote:
    analyst: str
    decision: str  # BUY | SELL | NO_TRADE | WAIT | VETO
    confidence: float
    reason: str
    risk: str = ""
    expected_edge: float | None = None
    weight: float = 1.0
    data_quality: str = "KNOWN"  # KNOWN | UNKNOWN | STALE | UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineStageResult:
    stage: str
    status: StageStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class TradeThesis:
    symbol: str
    why: str
    catalyst: str
    horizon: str
    invalidation: str
    target: float | None
    stop: float | None
    expected_edge: float | None
    risk: str
    confidence: float
    analyst_votes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfessionalDecision:
    decision_id: str
    symbol: str
    decision: str
    confidence: float
    expected_edge: float | None
    risk_reward: float | None
    market_regime: str
    signal_quality: float
    liquidity_score: float | None
    execution_score: float | None
    portfolio_fit: float | None
    risk_status: str
    entry_action: str  # BUY | WAIT | NO_TRADE
    order_type: str  # MARKET | LIMIT | PASSIVE_LIMIT | AGGRESSIVE_LIMIT
    committee_votes: list[dict[str, Any]] = field(default_factory=list)
    pipeline: list[dict[str, Any]] = field(default_factory=list)
    thesis: dict[str, Any] | None = None
    veto: bool = False
    veto_reason: str = ""
    session_mode: str = DeskSessionMode.INTRADAY.value
    created_at: str = field(default_factory=_utc)
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def new_id() -> str:
        return f"desk-{uuid4().hex[:12]}"
