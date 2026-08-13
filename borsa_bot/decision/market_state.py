"""Normalized market observation — missing fields are UNKNOWN, never silent 0."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DataQuality(str, Enum):
    OK = "OK"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    MISSING = "MISSING"


@dataclass
class FieldValue:
    value: float | str | None
    quality: DataQuality = DataQuality.OK
    source: str = ""
    note: str = ""

    def known(self) -> bool:
        return self.quality == DataQuality.OK and self.value is not None


def unknown(note: str = "missing", source: str = "") -> FieldValue:
    return FieldValue(value=None, quality=DataQuality.UNKNOWN, source=source, note=note)


def known(value: float | str, source: str = "") -> FieldValue:
    return FieldValue(value=value, quality=DataQuality.OK, source=source)


@dataclass
class PriceState:
    last: FieldValue = field(default_factory=lambda: unknown("price"))
    bid: FieldValue = field(default_factory=lambda: unknown("bid"))
    ask: FieldValue = field(default_factory=lambda: unknown("ask"))


@dataclass
class VolumeState:
    last: FieldValue = field(default_factory=lambda: unknown("volume"))
    avg20: FieldValue = field(default_factory=lambda: unknown("vol_sma20"))


@dataclass
class VolatilityState:
    atr: FieldValue = field(default_factory=lambda: unknown("atr"))
    atr_pct: FieldValue = field(default_factory=lambda: unknown("atr_pct"))


@dataclass
class TrendState:
    label: FieldValue = field(default_factory=lambda: unknown("trend"))
    ema_slope: FieldValue = field(default_factory=lambda: unknown("ema_slope"))


@dataclass
class MomentumState:
    rsi: FieldValue = field(default_factory=lambda: unknown("rsi"))
    macd_hist: FieldValue = field(default_factory=lambda: unknown("macd"))


@dataclass
class LiquidityState:
    spread_pct: FieldValue = field(default_factory=lambda: unknown("spread"))
    score: FieldValue = field(default_factory=lambda: unknown("liquidity_score"))


@dataclass
class RegimeState:
    regime: FieldValue = field(default_factory=lambda: unknown("regime"))
    confidence: FieldValue = field(default_factory=lambda: unknown("regime_confidence"))


@dataclass
class PortfolioState:
    cash: FieldValue = field(default_factory=lambda: unknown("cash"))
    equity: FieldValue = field(default_factory=lambda: unknown("equity"))
    open_positions: FieldValue = field(default_factory=lambda: unknown("open_positions"))
    exposure_pct: FieldValue = field(default_factory=lambda: unknown("exposure"))
    drawdown_pct: FieldValue = field(default_factory=lambda: unknown("drawdown"))
    consecutive_losses: FieldValue = field(default_factory=lambda: unknown("consec_losses"))
    has_position: FieldValue = field(default_factory=lambda: unknown("has_position"))
    position_qty: FieldValue = field(default_factory=lambda: unknown("position_qty"))


@dataclass
class MarketState:
    symbol: str
    timestamp: float = field(default_factory=time.time)
    price: PriceState = field(default_factory=PriceState)
    volume: VolumeState = field(default_factory=VolumeState)
    volatility: VolatilityState = field(default_factory=VolatilityState)
    trend: TrendState = field(default_factory=TrendState)
    momentum: MomentumState = field(default_factory=MomentumState)
    liquidity: LiquidityState = field(default_factory=LiquidityState)
    regime: RegimeState = field(default_factory=RegimeState)
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    recent_trades: list[dict[str, Any]] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)

    def collect_unknowns(self) -> list[str]:
        found: list[str] = []

        def walk(prefix: str, obj: Any) -> None:
            if isinstance(obj, FieldValue):
                if not obj.known():
                    found.append(prefix)
                return
            if hasattr(obj, "__dataclass_fields__"):
                for name in obj.__dataclass_fields__:
                    walk(f"{prefix}.{name}" if prefix else name, getattr(obj, name))

        walk("", self.price)
        walk("volume", self.volume)
        walk("volatility", self.volatility)
        walk("trend", self.trend)
        walk("momentum", self.momentum)
        walk("liquidity", self.liquidity)
        walk("regime", self.regime)
        walk("portfolio", self.portfolio)
        self.unknown_fields = found
        return found

    def to_dict(self) -> dict[str, Any]:
        self.collect_unknowns()
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "unknown_fields": list(self.unknown_fields),
            "price": asdict(self.price),
            "volume": asdict(self.volume),
            "volatility": asdict(self.volatility),
            "trend": asdict(self.trend),
            "momentum": asdict(self.momentum),
            "liquidity": asdict(self.liquidity),
            "regime": asdict(self.regime),
            "portfolio": asdict(self.portfolio),
            "recent_trades": list(self.recent_trades),
        }
