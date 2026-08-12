"""Position sizing under immutable hard caps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.reasons import RC_SIZE_CAPPED_TO_ZERO, RC_SIZE_WITHIN_HARD_MAX, DecisionReason


@dataclass
class PositionSizeResult:
    calculated_size: float
    capped_size: float
    notional: float
    within_hard_max: bool
    reason: DecisionReason

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason"] = self.reason.to_dict()
        return d


def calculate_position_size(
    *,
    equity: float,
    price: float,
    risk_pct: float,
    stop_distance_pct: float,
    limits: ImmutableSafetyLimits,
    current_exposure_pct: float = 0.0,
    confidence: float = 1.0,
) -> PositionSizeResult:
    """Compute size then enforce calculated_size <= hard_max_position_size.

    Bot never raises hard_max; only clamps down.
    """
    reason = DecisionReason(stage="POSITION_SIZING")
    if price <= 0 or equity <= 0:
        reason.add(RC_SIZE_CAPPED_TO_ZERO, "invalid price or equity", price=price, equity=equity)
        return PositionSizeResult(0.0, 0.0, 0.0, True, reason)

    stop = max(stop_distance_pct, 0.1)
    risk_budget = equity * (max(risk_pct, 0.0) / 100.0) * max(0.0, min(confidence, 1.0))
    raw_shares = risk_budget / (price * (stop / 100.0))

    # Exposure headroom
    headroom_pct = max(0.0, limits.hard_max_exposure_pct - current_exposure_pct)
    max_by_exposure = (equity * (headroom_pct / 100.0)) / price if price > 0 else 0.0
    max_by_notional = limits.hard_max_position_notional / price if price > 0 else 0.0

    calculated = max(0.0, raw_shares)
    capped = min(calculated, limits.hard_max_position_size, max_by_exposure, max_by_notional)
    capped = max(0.0, capped)
    notional = capped * price
    within = capped <= limits.hard_max_position_size + 1e-9

    if capped <= 0:
        reason.add(RC_SIZE_CAPPED_TO_ZERO, "size floored to zero by limits or headroom")
    else:
        reason.add(
            RC_SIZE_WITHIN_HARD_MAX,
            "size within hard max",
            calculated=calculated,
            capped=capped,
            hard_max=limits.hard_max_position_size,
        )

    return PositionSizeResult(
        calculated_size=calculated,
        capped_size=capped,
        notional=notional,
        within_hard_max=within,
        reason=reason,
    )
