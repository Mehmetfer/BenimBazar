"""Trading regime classification with confidence + evidence (used by decision pipeline)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from decision.market_state import MarketState


class TradingRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeAssessment:
    regime: TradingRegime
    confidence: float
    evidence: list[str] = field(default_factory=list)
    input_features: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "input_features": dict(self.input_features),
            "timestamp": self.timestamp,
        }


def classify_trading_regime(state: MarketState) -> RegimeAssessment:
    features: dict[str, Any] = {}
    evidence: list[str] = []

    # Require core inputs; else UNKNOWN (not silent NEUTRAL-as-zero)
    if not state.price.last.known() or not state.trend.label.known():
        return RegimeAssessment(
            TradingRegime.UNKNOWN,
            0.0,
            evidence=["missing_price_or_trend"],
            input_features=features,
        )

    atr_pct = state.volatility.atr_pct.value if state.volatility.atr_pct.known() else None
    slope = state.trend.ema_slope.value if state.trend.ema_slope.known() else None
    trend = str(state.trend.label.value)
    spread = state.liquidity.spread_pct.value if state.liquidity.spread_pct.known() else None
    liq = state.liquidity.score.value if state.liquidity.score.known() else None

    features = {
        "atr_pct": atr_pct,
        "ema_slope": slope,
        "trend_label": trend,
        "spread_pct": spread,
        "liquidity_score": liq,
    }

    if atr_pct is None or slope is None:
        return RegimeAssessment(
            TradingRegime.UNKNOWN,
            0.2,
            evidence=["insufficient_features"],
            input_features=features,
        )

    if spread is not None and spread >= 1.5 or (liq is not None and liq <= 25):
        evidence.append("wide_spread_or_low_liquidity")
        return RegimeAssessment(TradingRegime.LOW_LIQUIDITY, 0.75, evidence, features)

    if atr_pct >= 4.0:
        evidence.append(f"atr_pct={atr_pct:.2f}>=4")
        return RegimeAssessment(TradingRegime.HIGH_VOLATILITY, 0.8, evidence, features)

    if trend == "BULL" and slope > 0.2:
        evidence.append("bull_ema_stack")
        conf = 0.7 + min(0.25, abs(slope) / 10)
        return RegimeAssessment(TradingRegime.TREND_UP, round(conf, 3), evidence, features)

    if trend == "BEAR" and slope < -0.2:
        evidence.append("bear_ema_stack")
        conf = 0.7 + min(0.25, abs(slope) / 10)
        return RegimeAssessment(TradingRegime.TREND_DOWN, round(conf, 3), evidence, features)

    evidence.append("no_clear_trend")
    return RegimeAssessment(TradingRegime.RANGE, 0.55, evidence, features)
