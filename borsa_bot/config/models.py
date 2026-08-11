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


class TimeHorizon(str, Enum):
    DAY_TRADE = "DAY_TRADE"
    SWING = "SWING"
    POSITION = "POSITION"
    LONG_TERM = "LONG_TERM"


class PlanState(str, Enum):
    WATCH = "WATCH"
    SETUP = "SETUP"
    READY = "READY"
    ENTRY_TRIGGERED = "ENTRY_TRIGGERED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ACTIVE = "ACTIVE"
    TARGET_1 = "TARGET_1"
    TARGET_2 = "TARGET_2"
    TARGET_3 = "TARGET_3"
    STOPPED = "STOPPED"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"


class FinalDecision(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    SELL_NOW = "SELL_NOW"
    PARTIAL_SELL = "PARTIAL_SELL"
    TRAILING_STOP = "TRAILING_STOP"


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
    cci20: float
    williams_r: float
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
    """Legacy compact plan — kept for RiskEngine / EV compatibility."""

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
class EntryZone:
    low: float
    high: float
    optimal: float
    label: str = "OPTIMAL"


@dataclass
class TargetLevel:
    price: float
    probability: float
    expected_return_pct: float
    resistance_note: str
    historical_hit_rate: float | None  # None = unavailable (honest)


@dataclass
class PlanVariant:
    name: str  # PULLBACK | BREAKOUT | SELL
    entry_zone: EntryZone | None
    trigger: float | None
    stop: float
    targets: list[TargetLevel]
    risk_reward: float
    expected_value: float
    confirmation: str
    stop_reason: str


@dataclass
class AITradePlan:
    """Full actionable plan. Creating a plan ≠ sending an order."""

    symbol: str
    side: str  # BUY/SELL
    current_price: float
    entry_price: float
    entry_zone: EntryZone
    stop_loss: float
    stop_reason: str
    target1: TargetLevel
    target2: TargetLevel
    target3: TargetLevel
    expected_return_pct: float
    maximum_risk_pct: float
    risk_reward: float
    confidence: float
    win_probability: float
    position_size: float
    max_risk_tl: float
    risk_per_share: float
    time_horizon: TimeHorizon
    holding_estimate: str
    strategy: str
    state: PlanState
    final_decision: FinalDecision
    plan_a: PlanVariant | None = None
    plan_b: PlanVariant | None = None
    preferred_plan: str = "PULLBACK"
    valid_until: str | None = None
    invalidation_rules: list[str] = field(default_factory=list)
    thesis: str = ""
    risk_notes: list[str] = field(default_factory=list)
    chase_warning: str | None = None
    existing_position_action: FinalDecision | None = None
    avg_cost: float | None = None
    partial_tp_hint: str | None = None
    trailing_hint: str | None = None
    disclaimer: str = (
        "Modelin mevcut verilere göre tahmini. Kesin kazanç garantisi yoktur. "
        "Trade plan emir değildir; Risk Engine + onay gerekir. LIVE default OFF."
    )
    risk_validated: bool = False
    risk_reject_reason: str = ""
    message_tr: str = ""
    sms_ascii: str = ""
    tts_tr: str = ""
    push_body: str = ""

    def to_legacy(self) -> TradePlan:
        return TradePlan(
            entry=round(self.entry_price, 2),
            stop=round(self.stop_loss, 2),
            target1=round(self.target1.price, 2),
            target2=round(self.target2.price, 2),
            target3=round(self.target3.price, 2),
            risk_reward=round(self.risk_reward, 2),
            quantity=float(self.position_size),
            t1_exit_pct=0.25,
            t2_exit_pct=0.25,
            t3_exit_pct=0.25,
            trail_remainder_pct=0.25,
        )


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
    factors: dict[str, float] = field(default_factory=dict)
    alpha_summary: dict = field(default_factory=dict)
    price_action: dict = field(default_factory=dict)
    universe_ok: bool = True
    universe_reason: str = "ok"
    risk_verdict: str = ""
    ai_trade_plan: Any | None = None  # AITradePlan — typed loosely to avoid cycle
    final_decision: str = ""


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
