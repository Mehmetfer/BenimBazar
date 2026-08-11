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
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"
    # backward-compatible alias used in older tests/docs
    SIDEWAYS = "NEUTRAL"


class SignalAction(str, Enum):
    AL = "AL"
    SAT = "SAT"
    BEKLE = "BEKLE"
    ALMA = "ALMA"
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WATCH = "WATCH"
    WAIT = "WAIT"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    NO_TRADE = "NO_TRADE"
    # legacy aliases
    HOLD = "WAIT"
    AVOID = "NO_TRADE"


class CapitalMode(str, Enum):
    NORMAL = "NORMAL"
    DEFENSIVE = "DEFENSIVE"
    HIGH_RISK = "HIGH_RISK"
    CAPITAL_PROTECTION = "CAPITAL_PROTECTION"
    KILL_SWITCH = "KILL_SWITCH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


class NewsSentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    HIGH_RISK = "HIGH_RISK"
    UNCERTAIN = "UNCERTAIN"


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
    ema100: float
    ema200: float
    sma20: float
    sma50: float
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
    stoch_rsi_k: float
    stoch_rsi_d: float
    vwap: float
    vol_sma20: float
    momentum10: float
    roc12: float
    obv: float
    mfi14: float
    cmf20: float
    support: float
    resistance: float
    pivot: float
    structure: str  # HH_HL / LH_LL / RANGE


@dataclass
class ScoreBundle:
    technical: float
    fundamental: float
    market: float
    sector: float
    momentum: float
    volume: float
    news: float
    liquidity: float
    risk: float
    ai_confidence: float
    final: float


@dataclass
class TradePlan:
    entry: float
    stop: float
    target1: float
    target2: float
    target3: float
    risk_reward: float
    quantity: float = 0.0
    t1_exit_pct: float = 0.25
    t2_exit_pct: float = 0.25
    t3_exit_pct: float = 0.25
    trail_remainder_pct: float = 0.25


@dataclass
class OpportunityMetrics:
    p_win: float
    expected_return_pct: float
    expected_loss_pct: float
    risk_reward: float
    expected_value: float
    volatility_pct: float
    drawdown_impact: float
    position_size_mult: float
    confidence: float


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
    scores: ScoreBundle | None = None
    trade_plan: TradePlan | None = None
    opportunity: OpportunityMetrics | None = None
    capital_mode: CapitalMode = CapitalMode.NORMAL
    decision: SignalAction = SignalAction.WAIT
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    indicators: dict[str, float] = field(default_factory=dict)
    strategy_votes: dict[str, str] = field(default_factory=dict)
    strategy_weights: dict[str, float] = field(default_factory=dict)
    mtf: dict[str, str] = field(default_factory=dict)
    conflict: bool = False


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


@dataclass
class FundamentalSnapshot:
    symbol: str
    pe: float | None = None
    pb: float | None = None
    ev_ebitda: float | None = None
    ev_sales: float | None = None
    net_debt: float | None = None
    debt_equity: float | None = None
    current_ratio: float | None = None
    roe: float | None = None
    roa: float | None = None
    net_margin: float | None = None
    op_margin: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    equity_growth: float | None = None
    fcf: float | None = None
    ocf: float | None = None
    dividend_yield: float | None = None
    available: bool = False


@dataclass
class NewsItem:
    symbol: str
    headline: str
    sentiment: NewsSentiment
    importance: float
    confidence: float
    price_impact: float
    sector_impact: float
    validity_hours: float
    available: bool = False
