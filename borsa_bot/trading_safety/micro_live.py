"""MICRO_LIVE hard caps — configuration cannot silently unbound them."""

from __future__ import annotations

from dataclasses import dataclass

# Absolute ceilings — env may only tighten, never exceed these.
MICRO_LIVE_ABS_MAX_ORDER_QTY = 1.0
MICRO_LIVE_ABS_MAX_NOTIONAL = 500.0
MICRO_LIVE_ABS_MAX_DAILY_LOSS_PCT = 0.5
MICRO_LIVE_ABS_MAX_TRADES_PER_DAY = 3
MICRO_LIVE_ABS_MAX_SYMBOLS = 2


@dataclass(frozen=True)
class MicroLiveLimits:
    max_order_qty: float = 1.0
    max_notional: float = 100.0
    max_daily_loss_pct: float = 0.25
    max_trades_per_day: int = 2
    allowed_symbols: tuple[str, ...] = ("THYAO",)

    def __post_init__(self) -> None:
        # Enforce absolute ceilings (frozen → object.__setattr__)
        object.__setattr__(self, "max_order_qty", min(float(self.max_order_qty), MICRO_LIVE_ABS_MAX_ORDER_QTY))
        object.__setattr__(self, "max_notional", min(float(self.max_notional), MICRO_LIVE_ABS_MAX_NOTIONAL))
        object.__setattr__(
            self,
            "max_daily_loss_pct",
            min(float(self.max_daily_loss_pct), MICRO_LIVE_ABS_MAX_DAILY_LOSS_PCT),
        )
        object.__setattr__(
            self,
            "max_trades_per_day",
            min(int(self.max_trades_per_day), MICRO_LIVE_ABS_MAX_TRADES_PER_DAY),
        )
        syms = tuple(s.upper() for s in self.allowed_symbols[:MICRO_LIVE_ABS_MAX_SYMBOLS])
        object.__setattr__(self, "allowed_symbols", syms or ("THYAO",))

    def check_order(self, *, symbol: str, qty: float, price: float, trades_today: int, daily_loss_pct: float) -> tuple[bool, str]:
        if symbol.upper() not in self.allowed_symbols:
            return False, f"MICRO_LIVE_SYMBOL_NOT_ALLOWED:{symbol}"
        if qty > self.max_order_qty + 1e-12:
            return False, "MICRO_LIVE_MAX_ORDER_QTY"
        if qty * price > self.max_notional + 1e-9:
            return False, "MICRO_LIVE_MAX_NOTIONAL"
        if trades_today >= self.max_trades_per_day:
            return False, "MICRO_LIVE_MAX_TRADES"
        if daily_loss_pct <= -self.max_daily_loss_pct:
            return False, "MICRO_LIVE_DAILY_LOSS"
        return True, "OK"
