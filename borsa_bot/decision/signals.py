"""GÖREV 13 — Signal fusion into a composite decision candidate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List

from decision.market_state import MarketState
from decision.regime import RegimeAssessment, TradingRegime


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


@dataclass
class AtomicSignal:
    source: str
    score: float  # -1 .. +1
    confidence: float  # 0 .. 1
    direction: SignalDirection
    timestamp: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "direction": self.direction.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


@dataclass
class CompositeSignal:
    direction: SignalDirection
    score: float
    confidence: float
    conflict: bool
    conflict_reasons: List[str] = field(default_factory=list)
    components: List[AtomicSignal] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "conflict": self.conflict,
            "conflict_reasons": list(self.conflict_reasons),
            "components": [c.to_dict() for c in self.components],
            "timestamp": self.timestamp,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def fuse_signals(
    state: MarketState,
    regime: RegimeAssessment,
    *,
    min_confidence: float = 0.45,
) -> CompositeSignal:
    """Fuse technical/momentum/trend/volume/regime/liquidity/risk into one composite."""
    ts = _now()
    components: List[AtomicSignal] = []

    # Trend (label: BULL/BEAR/RANGE + ema_slope)
    if state.trend.label.known() and state.trend.ema_slope.known():
        label = str(state.trend.label.value)
        slope = float(state.trend.ema_slope.value)
        strength = min(1.0, abs(slope) / 2.0)
        if label == "BULL" or slope > 0.2:
            score = strength if slope > 0 else 0.35
            direction = SignalDirection.BUY
        elif label == "BEAR" or slope < -0.2:
            score = -strength if slope < 0 else -0.35
            direction = SignalDirection.SELL
        else:
            score = 0.0
            direction = SignalDirection.HOLD
        conf = 0.55 + min(0.3, abs(slope) / 5.0)
        components.append(
            AtomicSignal(
                source="trend",
                score=_clamp(score),
                confidence=min(1.0, conf),
                direction=direction,
                timestamp=ts,
                reason=f"trend={label};slope={slope:.3f}",
            )
        )
    else:
        components.append(
            AtomicSignal(
                source="trend",
                score=0.0,
                confidence=0.0,
                direction=SignalDirection.NO_TRADE,
                timestamp=ts,
                reason="trend_unknown",
            )
        )

    # Momentum (RSI)
    if state.momentum.rsi.known():
        rsi = float(state.momentum.rsi.value)
        if rsi >= 70:
            score, direction, reason = -0.5, SignalDirection.SELL, "rsi_overbought"
        elif rsi <= 30:
            score, direction, reason = 0.5, SignalDirection.BUY, "rsi_oversold"
        else:
            score = (50 - rsi) / 50.0 * 0.3
            direction = (
                SignalDirection.BUY
                if score > 0
                else (SignalDirection.SELL if score < 0 else SignalDirection.HOLD)
            )
            reason = f"rsi={rsi:.1f}"
        components.append(
            AtomicSignal(
                source="momentum",
                score=_clamp(score),
                confidence=0.55,
                direction=direction,
                timestamp=ts,
                reason=reason,
            )
        )
    else:
        components.append(
            AtomicSignal(
                source="momentum",
                score=0.0,
                confidence=0.0,
                direction=SignalDirection.NO_TRADE,
                timestamp=ts,
                reason="momentum_unknown",
            )
        )

    # Volume ratio (last / avg20)
    if state.volume.last.known() and state.volume.avg20.known():
        last_v = float(state.volume.last.value)
        avg_v = float(state.volume.avg20.value)
        vr = last_v / avg_v if avg_v > 0 else 1.0
        score = _clamp((vr - 1.0) * 0.4)
        components.append(
            AtomicSignal(
                source="volume",
                score=score,
                confidence=0.5,
                direction=(
                    SignalDirection.BUY
                    if score > 0.1
                    else (SignalDirection.SELL if score < -0.1 else SignalDirection.HOLD)
                ),
                timestamp=ts,
                reason=f"volume_ratio={vr:.2f}",
            )
        )
    else:
        components.append(
            AtomicSignal(
                source="volume",
                score=0.0,
                confidence=0.2,
                direction=SignalDirection.HOLD,
                timestamp=ts,
                reason="volume_unknown",
            )
        )

    # Regime (must be consumed — not dead)
    regime_score = 0.0
    regime_dir = SignalDirection.HOLD
    if regime.regime == TradingRegime.TREND_UP:
        regime_score, regime_dir = 0.55, SignalDirection.BUY
    elif regime.regime == TradingRegime.TREND_DOWN:
        regime_score, regime_dir = -0.55, SignalDirection.SELL
    elif regime.regime == TradingRegime.RANGE:
        regime_score, regime_dir = 0.0, SignalDirection.HOLD
    elif regime.regime in (
        TradingRegime.HIGH_VOLATILITY,
        TradingRegime.LOW_LIQUIDITY,
        TradingRegime.UNKNOWN,
    ):
        regime_score, regime_dir = 0.0, SignalDirection.NO_TRADE
    components.append(
        AtomicSignal(
            source="regime",
            score=regime_score,
            confidence=regime.confidence,
            direction=regime_dir,
            timestamp=ts,
            reason=f"regime={regime.regime.value}",
        )
    )

    # Liquidity score is 0–100 in MarketState
    if state.liquidity.score.known():
        liq = float(state.liquidity.score.value)
        if liq < 35:
            components.append(
                AtomicSignal(
                    source="liquidity",
                    score=0.0,
                    confidence=0.8,
                    direction=SignalDirection.NO_TRADE,
                    timestamp=ts,
                    reason=f"low_liquidity={liq:.1f}",
                )
            )
        else:
            components.append(
                AtomicSignal(
                    source="liquidity",
                    score=0.1,
                    confidence=0.5,
                    direction=SignalDirection.HOLD,
                    timestamp=ts,
                    reason=f"liquidity_ok={liq:.1f}",
                )
            )
    else:
        components.append(
            AtomicSignal(
                source="liquidity",
                score=0.0,
                confidence=0.0,
                direction=SignalDirection.NO_TRADE,
                timestamp=ts,
                reason="liquidity_unknown",
            )
        )

    # Risk / portfolio exposure (percent 0–100)
    if state.portfolio.exposure_pct.known():
        exp = float(state.portfolio.exposure_pct.value)
        if exp >= 85:
            components.append(
                AtomicSignal(
                    source="risk",
                    score=0.0,
                    confidence=0.9,
                    direction=SignalDirection.NO_TRADE,
                    timestamp=ts,
                    reason=f"high_exposure={exp:.1f}",
                )
            )
        else:
            components.append(
                AtomicSignal(
                    source="risk",
                    score=0.05,
                    confidence=0.4,
                    direction=SignalDirection.HOLD,
                    timestamp=ts,
                    reason=f"exposure={exp:.1f}",
                )
            )
    else:
        components.append(
            AtomicSignal(
                source="risk",
                score=0.0,
                confidence=0.2,
                direction=SignalDirection.HOLD,
                timestamp=ts,
                reason="exposure_unknown",
            )
        )

    conflict_reasons: List[str] = []
    buyish = [c for c in components if c.direction == SignalDirection.BUY and c.confidence >= 0.4]
    sellish = [c for c in components if c.direction == SignalDirection.SELL and c.confidence >= 0.4]
    blockers = [c for c in components if c.direction == SignalDirection.NO_TRADE and c.confidence >= 0.4]

    if buyish and sellish:
        conflict_reasons.append("buy_vs_sell_conflict")
    if buyish and any(b.source in ("liquidity", "risk", "regime") for b in blockers):
        conflict_reasons.append("buy_blocked_by_risk_or_liquidity")
    if any(c.source == "trend" and c.direction == SignalDirection.NO_TRADE for c in components):
        conflict_reasons.append("missing_core_trend_data")

    weighted = 0.0
    weight_sum = 0.0
    for c in components:
        w = max(c.confidence, 0.05)
        weighted += c.score * w
        weight_sum += w
    score = weighted / weight_sum if weight_sum else 0.0
    confidence = min(1.0, weight_sum / max(len(components), 1))

    if blockers and (buyish or abs(score) > 0.2):
        direction = SignalDirection.NO_TRADE
        conflict_reasons.append("blocker_forces_no_trade")
        confidence = min(confidence, 0.35)
    elif conflict_reasons:
        direction = SignalDirection.NO_TRADE
        confidence = min(confidence, 0.4)
    elif confidence < min_confidence:
        direction = SignalDirection.NO_TRADE
        conflict_reasons.append("insufficient_confidence")
    elif score >= 0.2:
        direction = SignalDirection.BUY
    elif score <= -0.2:
        direction = SignalDirection.SELL
    else:
        direction = SignalDirection.HOLD

    return CompositeSignal(
        direction=direction,
        score=_clamp(score),
        confidence=round(confidence, 4),
        conflict=bool(conflict_reasons),
        conflict_reasons=conflict_reasons,
        components=components,
        timestamp=ts,
    )
