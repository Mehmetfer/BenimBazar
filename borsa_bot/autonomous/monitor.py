"""Position monitor + exit helpers — trailing stops, partial TPs, full exits."""

from __future__ import annotations

import math
from typing import Any

from config.models import OrderRequest
from config.settings import settings
from indicators.engine import compute_indicators
from profit.protection import ProfitProtectState, initial_protect, update_profit_protection


def _load_state(pos: Any, trading: Any) -> ProfitProtectState:
    meta = trading.ledger.get_protect_meta(pos.symbol)
    if meta:
        partial = meta.get("partial_exits_done") or [False, False, False]
        if len(partial) < 3:
            partial = list(partial) + [False] * (3 - len(partial))
        return ProfitProtectState(
            stop=float(meta.get("stop") or pos.stop_price or pos.avg_cost * 0.97),
            trailing_stop=meta.get("trailing_stop"),
            breakeven_armed=bool(meta.get("breakeven_armed")),
            partial_exits_done=(bool(partial[0]), bool(partial[1]), bool(partial[2])),
            reason=str(meta.get("reason") or "restored"),
        )
    return initial_protect(pos.avg_cost, pos.stop_price or pos.avg_cost * 0.97)


def _save_state(trading: Any, symbol: str, state: ProfitProtectState) -> None:
    trading.ledger.set_protect_meta(
        symbol,
        {
            "stop": state.stop,
            "trailing_stop": state.trailing_stop,
            "breakeven_armed": state.breakeven_armed,
            "partial_exits_done": list(state.partial_exits_done),
            "reason": state.reason,
        },
    )


def monitor_and_exit(trading: Any, *, execution_mode: str = "PAPER") -> list[dict]:
    """Update trailing stops, execute partial TPs, then run stop/target exits.

    SHADOW: detect would-exit only (no sells).
    LIVE: still blocked by PaperBroker/LiveBrokerDisabled unless unlocked.
    """
    mode = (execution_mode or "PAPER").upper()
    trail_updates: list[dict] = []
    partial_exits: list[dict] = []

    for pos in list(trading.ledger.positions()):
        try:
            bars = trading.provider.get_bars(pos.symbol, 80)
            ind = compute_indicators(bars)
            if ind is None or pos.stop_price is None:
                continue
            quote = trading.provider.get_quote(pos.symbol)
            state = _load_state(pos, trading)
            plan = trading.ledger.get_protect_meta(pos.symbol).get("targets") or {}
            t1 = float(plan.get("t1") or pos.target_price or (pos.avg_cost * 1.02))
            t2 = float(plan.get("t2") or t1 * 1.01)
            t3 = float(plan.get("t3") or t2 * 1.01)
            new_state, partial_frac = update_profit_protection(
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
                with trading.ledger._connect() as c:  # noqa: SLF001
                    c.execute(
                        "UPDATE positions SET stop_price=? WHERE symbol=?",
                        (float(new_state.stop), pos.symbol),
                    )
                trail_updates.append(
                    {
                        "symbol": pos.symbol,
                        "old_stop": pos.stop_price,
                        "new_stop": new_state.stop,
                        "reason": new_state.reason,
                    }
                )
                pos.stop_price = new_state.stop

            if partial_frac and partial_frac > 0 and mode != "SHADOW":
                sell_qty = max(1, int(math.floor(pos.quantity * float(partial_frac))))
                if sell_qty >= pos.quantity:
                    sell_qty = max(1, int(pos.quantity) - 1) if pos.quantity > 1 else int(pos.quantity)
                if sell_qty > 0 and sell_qty <= pos.quantity:
                    order = OrderRequest(
                        symbol=pos.symbol,
                        side="SELL",
                        quantity=float(sell_qty),
                        price=quote.price,
                        reason="partial_tp",
                        client_order_id=f"PARTIAL:{pos.symbol}:{quote.price}",
                    )
                    result = trading.broker.submit(order, pos.sector)
                    partial_exits.append(
                        {
                            "symbol": pos.symbol,
                            "fraction": partial_frac,
                            "quantity": sell_qty,
                            "ok": result.ok,
                            "status": result.status,
                        }
                    )
            _save_state(trading, pos.symbol, new_state)
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
        out: list[dict] = []
        if trail_updates:
            out.append({"trail_updates": trail_updates})
        if partial_exits:
            out.append({"partial_exits": partial_exits})
        out.append({"would_exits": would})
        return out

    exits = trading._monitor_exits_core()
    if trail_updates:
        exits.append({"trail_updates": trail_updates})
    if partial_exits:
        exits.append({"partial_exits": partial_exits})
    return exits
