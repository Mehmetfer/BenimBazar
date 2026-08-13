"""Helpers to build MarketState fixtures without inventing silent zeros for unknowns."""

from __future__ import annotations

from decision.market_state import (
    LiquidityState,
    MarketState,
    MomentumState,
    PortfolioState,
    PriceState,
    RegimeState,
    TrendState,
    VolatilityState,
    VolumeState,
    known,
    unknown,
)


def bull_liquid_state(symbol: str = "TEST") -> MarketState:
    return MarketState(
        symbol=symbol,
        price=PriceState(last=known(100.0, "t"), bid=known(99.9, "t"), ask=known(100.1, "t")),
        volume=VolumeState(last=known(2_000_000.0, "t"), avg20=known(1_500_000.0, "t")),
        volatility=VolatilityState(atr=known(1.5, "t"), atr_pct=known(1.5, "t")),
        trend=TrendState(label=known("BULL", "t"), ema_slope=known(0.8, "t")),
        momentum=MomentumState(rsi=known(55.0, "t"), macd_hist=known(0.2, "t")),
        liquidity=LiquidityState(spread_pct=known(0.1, "t"), score=known(90.0, "t")),
        regime=RegimeState(regime=known("TREND_UP", "t"), confidence=known(0.8, "t")),
        portfolio=PortfolioState(
            cash=known(50_000.0, "t"),
            equity=known(50_000.0, "t"),
            open_positions=known(0.0, "t"),
            exposure_pct=known(10.0, "t"),
            drawdown_pct=known(1.0, "t"),
            consecutive_losses=known(0.0, "t"),
            has_position=known(0.0, "t"),
            position_qty=known(0.0, "t"),
        ),
    )


def sparse_unknown_state(symbol: str = "TEST") -> MarketState:
    """Most fields intentionally UNKNOWN — must not become 0."""
    return MarketState(symbol=symbol)
