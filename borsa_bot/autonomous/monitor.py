"""Position monitor + exit helpers — wraps TradingService.monitor_exits and ATR trail updates."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from indicators.engine import compute_indicators
from profit.protection import initial_protect, update_profit_protection


def monitor_and_exit(trading: Any, *, execution_mode: str = "PAPER") -> list[dict]:
    """Update trailing stops where possible, then run existing exit monitor.

    SHADOW: detect would-exit only (no sells).
    LIVE: still blocked by PaperBroker/LiveBrokerDisabled unless unlocked.
    """
    mode = (execution_mode or "PAPER").upper()
    trail_updates: list[dict] = []

    for pos in list(trading.ledger.positions()):
        try:
            bars = trading.provider.get_bars(pos.symbol, 80)
            ind = compute_indicators(bars)
            if ind is None or pos.stop_price is None:
                continue
            quote = trading.provider.get_quote(pos.symbol)
            state = initial_protect(pos.avg_cost, pos.stop_price)
            # Approximate T1/T2/T3 from target if present
            t1 = pos.target_price or (pos.avg_cost * 1.02)
            t2 = t1 * 1.01
            t3 = t2 * 1.01
            new_state, _partial = update_profit_protection(
                entry=pos.avg_cost,
                price=quote.price,
                stop=pos.stop_price,
                ind=ind,
                t1=t1,
                t2=t2,
                t3=t3,
                state=state,
                momentum_ok=ind.ema21 >= ind.ema50,
                cfg=settings,
            )
            if new_state.stop > (pos.stop_price or 0):
                # Persist tighter stop via SQL update (minimal ledger touch)
                with trading.ledger._connect() as c:  # noqa: SLF001 — intentional stop trail persist
                    c.execute(
                        "UPDATE positions SET stop_price=? WHERE symbol=?",
                        (float(new_state.stop), pos.symbol),
                    )
                trail_updates.append(
                    {"symbol": pos.symbol, "old_stop": pos.stop_price, "new_stop": new_state.stop, "reason": new_state.reason}
                )
                pos.stop_price = new_state.stop
        except Exception:  # noqa: BLE001
            continue

    if mode == "SHADOW":
        would: list[dict] = []
        trading.tick()
        for pos in list(trading.ledger.positions()):
            quote = trading.provider.get_quote(pos.symbol)
            kind = None
            if pos.stop_price is not None and quote.price <= pos.stop_price:
                kind = "STOP_LOSS"
            elif pos.target_price is not None and quote.price >= pos.target_price:
                kind = "TAKE_PROFIT"
            if kind:
                would.append(
                    {
                        "ok": True,
                        "shadow": True,
                        "would": kind,
                        "symbol": pos.symbol,
                        "price": quote.price,
                        "qty": pos.quantity,
                    }
                )
        return [{"trail_updates": trail_updates, "would_exits": would}]

    exits = trading.monitor_exits()
    if trail_updates:
        exits.append({"trail_updates": trail_updates})
    return exits
