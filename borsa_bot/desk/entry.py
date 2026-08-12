"""Entry engine — BUY vs WAIT based on execution quality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntryPlan:
    action: str  # BUY | WAIT | NO_TRADE
    entry_price: float | None
    entry_zone: tuple[float, float] | None
    entry_quality: float
    expected_slippage_bps: float
    spread_pct: float | None
    liquidity_score: float | None
    urgency: str  # LOW | MEDIUM | HIGH
    order_type: str  # MARKET | LIMIT | PASSIVE_LIMIT | AGGRESSIVE_LIMIT
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "entry_price": self.entry_price,
            "entry_zone": list(self.entry_zone) if self.entry_zone else None,
            "entry_quality": round(self.entry_quality, 1),
            "expected_slippage_bps": round(self.expected_slippage_bps, 2),
            "spread_pct": self.spread_pct,
            "liquidity_score": self.liquidity_score,
            "urgency": self.urgency,
            "order_type": self.order_type,
            "reason": self.reason,
        }


def evaluate_entry(
    *,
    price: float,
    bid: float | None,
    ask: float | None,
    spread_pct: float | None,
    liquidity_score: float | None,
    signal_decision: str,
    consensus_decision: str,
) -> EntryPlan:
    """Strong signal + poor execution → WAIT."""
    if consensus_decision != "BUY" and signal_decision not in {"BUY", "STRONG_BUY", "AL"}:
        return EntryPlan(
            action="NO_TRADE",
            entry_price=price,
            entry_zone=None,
            entry_quality=0.0,
            expected_slippage_bps=0.0,
            spread_pct=spread_pct,
            liquidity_score=liquidity_score,
            urgency="LOW",
            order_type="LIMIT",
            reason="consensus_not_buy",
        )

    sp = float(spread_pct) if spread_pct is not None else 0.25
    liq = float(liquidity_score) if liquidity_score is not None else 50.0
    slip_bps = sp * 50 + max(0, (60 - liq) * 0.5)

    quality = 85.0
    if sp > 0.8:
        quality -= 25
    if sp > 1.5:
        quality -= 20
    if liq < 40:
        quality -= 30
    elif liq < 55:
        quality -= 10
    quality = max(0.0, min(100.0, quality))

    mid = price
    if bid and ask and bid > 0 and ask > bid:
        mid = (bid + ask) / 2.0
    zone_lo = mid * (1 - sp / 200)
    zone_hi = mid * (1 + sp / 400)

    if quality < 45:
        return EntryPlan(
            action="WAIT",
            entry_price=mid,
            entry_zone=(round(zone_lo, 4), round(zone_hi, 4)),
            entry_quality=quality,
            expected_slippage_bps=slip_bps,
            spread_pct=spread_pct,
            liquidity_score=liquidity_score,
            urgency="LOW",
            order_type="PASSIVE_LIMIT",
            reason="signal_strong_execution_poor",
        )

    if liq >= 70 and sp < 0.35:
        order_type = "AGGRESSIVE_LIMIT"
        urgency = "HIGH"
    elif liq >= 50:
        order_type = "LIMIT"
        urgency = "MEDIUM"
    else:
        order_type = "PASSIVE_LIMIT"
        urgency = "LOW"

    # Never recommend MARKET on wide spread / low liquidity
    if liq < 35 or sp > 1.2:
        order_type = "PASSIVE_LIMIT"

    return EntryPlan(
        action="BUY",
        entry_price=round(mid, 4),
        entry_zone=(round(zone_lo, 4), round(zone_hi, 4)),
        entry_quality=quality,
        expected_slippage_bps=slip_bps,
        spread_pct=spread_pct,
        liquidity_score=liquidity_score,
        urgency=urgency,
        order_type=order_type,
        reason="entry_quality_ok",
    )
