from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketRegime(str, Enum):
    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"


class SignalAction(str, Enum):
    AL = "AL"
    SAT = "SAT"
    BEKLE = "BEKLE"
    ALMA = "ALMA"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int = 0


@dataclass
class QuoteSnapshot:
    symbol: str
    name: str
    sector: str
    price: float
    bid: float
    ask: float
    volume: float
    trades: int
    ts: datetime

    @property
    def spread(self) -> float:
        return max(0.0, self.ask - self.bid)

    @property
    def spread_pct(self) -> float:
        mid = (self.ask + self.bid) / 2 if self.ask and self.bid else self.price
        return (self.spread / mid * 100) if mid else 0.0


@dataclass
class IndicatorSet:
    ema9: float
    ema21: float
    ema50: float
    ema200: float
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    atr14: float
    adx14: float
    stoch_k: float
    stoch_d: float
    vwap: float
    vol_sma20: float
    momentum10: float


@dataclass
class SymbolDecision:
    symbol: str
    name: str
    sector: str
    price: float
    trend: str
    buy_score: float
    sell_score: float
    ai_confidence: float
    risk: RiskLevel
    signal: SignalAction
    regime: MarketRegime
    stop_price: float | None
    target_price: float | None
    explanation: str
    indicators: dict[str, float] = field(default_factory=dict)
    strategy_votes: dict[str, str] = field(default_factory=dict)


@dataclass
class OrderRequest:
    symbol: str
    side: str  # BUY/SELL
    quantity: float
    price: float
    reason: str
    stop_price: float | None = None
    target_price: float | None = None
    client_order_id: str | None = None


@dataclass
class OrderResult:
    ok: bool
    order_id: str | None
    status: str
    message: str
    fill_price: float | None = None
    quantity: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
