from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from config.models import utc_now


class TimeHorizon(str, Enum):
    H1 = "1H"
    H3 = "3H"
    D1 = "1D"
    D3 = "3D"
    W1 = "1W"
    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    Y1 = "1Y"


# Seconds until evaluation is due (config-overridable via settings later)
HORIZON_SECONDS: dict[TimeHorizon, int] = {
    TimeHorizon.H1: 3600,
    TimeHorizon.H3: 3 * 3600,
    TimeHorizon.D1: 24 * 3600,
    TimeHorizon.D3: 3 * 24 * 3600,
    TimeHorizon.W1: 7 * 24 * 3600,
    TimeHorizon.M1: 30 * 24 * 3600,
    TimeHorizon.M3: 90 * 24 * 3600,
    TimeHorizon.M6: 180 * 24 * 3600,
    TimeHorizon.Y1: 365 * 24 * 3600,
}

DEFAULT_ACTIVE_HORIZONS = (
    TimeHorizon.H1,
    TimeHorizon.H3,
    TimeHorizon.D1,
    TimeHorizon.D3,
    TimeHorizon.W1,
)


class SampleTier(str, Enum):
    INSUFFICIENT = "INSUFFICIENT_DATA"
    PROVISIONAL = "PROVISIONAL"
    VALIDATED = "VALIDATED"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"


class ReliabilityGrade(str, Enum):
    S = "S"
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    INSUFFICIENT = "INSUFFICIENT"


class TradePlanOutcome(str, Enum):
    STOP_HIT = "STOP_HIT"
    TARGET_1_HIT = "TARGET_1_HIT"
    TARGET_2_HIT = "TARGET_2_HIT"
    TARGET_3_HIT = "TARGET_3_HIT"
    TIMEOUT = "TIMEOUT"
    OPEN = "OPEN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HorizonForecast:
    """Immutable point-in-time forecast for one horizon. MODEL_FORECAST — not a guarantee."""

    horizon: str
    direction: str  # UP | DOWN | FLAT
    forecast_return_pct: float
    forecast_price: float
    low_return_pct: float
    base_return_pct: float
    high_return_pct: float
    probability: float  # CURRENT FORECAST PROBABILITY (0-1)
    confidence: float  # 0-100 display confidence for this horizon
    uncertainty: str  # LOW | MEDIUM | HIGH


@dataclass
class PredictionRecord:
    """Immutable prediction snapshot. Never mutate after insert."""

    prediction_id: str
    timestamp: str
    symbol: str
    price_at_prediction: float
    signal: str
    confidence: float
    probability: float
    entry_price: float | None
    stop_loss: float | None
    target_1: float | None
    target_2: float | None
    target_3: float | None
    strategy: str
    market_regime: str
    sector: str
    time_horizon_primary: str
    model_version: str
    strategy_version: str
    features_snapshot: dict[str, Any]
    forecasts: list[HorizonForecast]
    is_favorite: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["forecasts"] = [asdict(f) if not isinstance(f, dict) else f for f in self.forecasts]
        return d


@dataclass
class HorizonEvaluation:
    prediction_id: str
    symbol: str
    horizon: str
    evaluated_at: str
    price_at_prediction: float
    forecast_price: float
    forecast_return_pct: float
    actual_price: float
    actual_return_pct: float
    return_error_pp: float
    direction_forecast: str
    direction_actual: str
    direction_correct: bool
    target_hit: bool | None
    abs_error_pct: float
    confidence: float
    probability: float
    strategy: str
    market_regime: str
    sector: str
    model_version: str
    prediction_quality_score: float
    error_category: str | None = None


@dataclass
class ReliabilityReport:
    scope: str  # overall | horizon | symbol | strategy | sector | regime | model
    key: str
    grade: str
    directional_accuracy: float | None
    historical_accuracy_pct: float | None  # HISTORICAL FORECAST ACCURACY (distinct from current probability)
    calibration_note: str
    brier_score: float | None
    sample_size: int
    sample_tier: str
    last_20: float | None
    last_50: float | None
    last_100: float | None
    degradation: bool
    mae: float | None
    note: str = (
        "Historical accuracy ≠ current forecast probability. "
        "No profit guarantee. Insufficient samples → INSUFFICIENT."
    )

    def to_dict(self) -> dict:
        return asdict(self)
