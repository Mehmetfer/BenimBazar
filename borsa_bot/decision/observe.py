"""Build MarketState from provider + ledger — never invent zeros for missing data."""

from __future__ import annotations

from typing import Any

from decision.market_state import (
    DataQuality,
    FieldValue,
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
from decision.regime import classify_trading_regime
from indicators.engine import compute_indicators
from market_regime.engine import trend_label


def observe_market(
    *,
    provider: Any,
    ledger: Any | None,
    symbol: str,
    regime_hint: str | None = None,
) -> MarketState:
    state = MarketState(symbol=symbol)
    try:
        quote = provider.get_quote(symbol)
    except Exception as exc:  # noqa: BLE001
        state.price.last = unknown(f"quote_error:{exc}", "provider")
        state.collect_unknowns()
        return state

    state.price = PriceState(
        last=known(float(quote.price), "quote"),
        bid=known(float(getattr(quote, "bid", quote.price)), "quote")
        if getattr(quote, "bid", None) is not None
        else unknown("bid", "quote"),
        ask=known(float(getattr(quote, "ask", quote.price)), "quote")
        if getattr(quote, "ask", None) is not None
        else unknown("ask", "quote"),
    )
    vol = float(getattr(quote, "volume", 0) or 0)
    state.volume.last = known(vol, "quote") if vol > 0 else unknown("volume<=0", "quote")
    spread = float(getattr(quote, "spread_pct", 0) or 0)
    state.liquidity.spread_pct = (
        known(spread, "quote") if spread >= 0 else unknown("spread", "quote")
    )

    bars = provider.get_bars(symbol, 220)
    ind = compute_indicators(bars) if bars else None
    if ind is None:
        state.volatility.atr = unknown("indicators", "indicators")
        state.trend.label = unknown("indicators", "indicators")
        state.momentum.rsi = unknown("indicators", "indicators")
    else:
        price = float(quote.price)
        atr = float(ind.atr14)
        state.volatility.atr = known(atr, "indicators")
        state.volatility.atr_pct = known(atr / price * 100 if price else None, "indicators") if price else unknown("price", "indicators")
        if state.volatility.atr_pct.value is None:
            state.volatility.atr_pct = unknown("atr_pct", "indicators")
        state.trend.label = known(trend_label(ind), "indicators")
        slope = (ind.ema21 - ind.ema50) / ind.ema50 * 100 if ind.ema50 else None
        state.trend.ema_slope = known(float(slope), "indicators") if slope is not None else unknown("ema50", "indicators")
        state.momentum.rsi = known(float(ind.rsi14), "indicators")
        state.momentum.macd_hist = known(float(getattr(ind, "macd_hist", 0.0) or 0.0), "indicators")
        if ind.vol_sma20:
            state.volume.avg20 = known(float(ind.vol_sma20), "indicators")
        else:
            state.volume.avg20 = unknown("vol_sma20", "indicators")

    # Liquidity score soft
    if state.liquidity.spread_pct.known():
        sp = float(state.liquidity.spread_pct.value)
        score = 90.0 if sp < 0.3 else 70.0 if sp < 0.8 else 40.0 if sp < 1.5 else 15.0
        state.liquidity.score = known(score, "derived")
    else:
        state.liquidity.score = unknown("spread", "derived")

    # Regime overlay (G12)
    reg = classify_trading_regime(state)
    state.regime = RegimeState(
        regime=known(reg.regime.value, "regime_engine"),
        confidence=known(reg.confidence, "regime_engine"),
    )
    if regime_hint:
        state.regime.regime = known(regime_hint, "hint")

    if ledger is not None:
        try:
            cash = float(ledger.cash)
            equity = float(ledger.equity())
            opens = int(ledger.open_position_count())
            dd = float(ledger.drawdown_pct())
            losses = int(ledger.consecutive_losses())
            pos = ledger.get_position(symbol)
            state.portfolio = PortfolioState(
                cash=known(cash, "ledger"),
                equity=known(equity, "ledger"),
                open_positions=known(float(opens), "ledger"),
                exposure_pct=known((1 - cash / equity) * 100 if equity else None, "ledger")
                if equity
                else unknown("equity", "ledger"),
                drawdown_pct=known(dd, "ledger"),
                consecutive_losses=known(float(losses), "ledger"),
                has_position=known(1.0 if pos else 0.0, "ledger"),
                position_qty=known(float(pos.quantity) if pos else 0.0, "ledger"),
            )
            if state.portfolio.exposure_pct.value is None:
                state.portfolio.exposure_pct = unknown("exposure", "ledger")
            # recent sells
            with ledger._connect() as conn:
                rows = conn.execute(
                    "SELECT symbol, pnl, ts FROM trades WHERE side='SELL' ORDER BY id DESC LIMIT 10"
                ).fetchall()
                state.recent_trades = [
                    {"symbol": r["symbol"], "pnl": float(r["pnl"]), "ts": r["ts"]} for r in rows
                ]
        except Exception as exc:  # noqa: BLE001
            state.portfolio.cash = unknown(f"ledger:{exc}", "ledger")
    else:
        state.portfolio = PortfolioState()

    # Freshness
    try:
        meta = provider.source_meta(30)
        if getattr(meta, "freshness", None) and str(meta.freshness.value) in {"STALE", "DISCONNECTED", "NO_DATA"}:
            state.price.last.quality = DataQuality.STALE
            state.price.last.note = str(meta.freshness.value)
    except Exception:  # noqa: BLE001
        pass

    state.collect_unknowns()
    return state
