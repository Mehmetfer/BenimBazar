"""Paper broker with production-like order FSM.

Default: full fill (tests / paper path). Optional partial fills via settings.
LIVE mode still blocked here — use ExecutionRouter for venue selection.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config.models import OrderRequest, OrderResult, utc_now
from config.settings import settings
from data.provenance import parse_data_source_kind
from portfolio.ledger import PortfolioLedger


class PaperOrderState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass
class PaperOrder:
    client_order_id: str
    order_id: str
    symbol: str
    side: str
    sector: str
    quantity: float
    price: float
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    state: PaperOrderState = PaperOrderState.CREATED
    stop_price: float | None = None
    target_price: float | None = None
    reason: str = ""
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())
    fills: list[dict[str, Any]] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled_qty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "filled_qty": self.filled_qty,
            "remaining": self.remaining,
            "avg_fill_price": self.avg_fill_price,
            "price": self.price,
            "state": self.state.value,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "fills": list(self.fills),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PaperBroker:
    ledger: PortfolioLedger
    recent_keys: dict[str, float] = field(default_factory=dict)
    data_source_kind: str = "SIMULATED"
    open_orders: dict[str, PaperOrder] = field(default_factory=dict)  # by client_order_id
    orders_by_id: dict[str, PaperOrder] = field(default_factory=dict)

    def _duplicate(self, key: str) -> bool:
        now = time.time()
        self.recent_keys = {k: t for k, t in self.recent_keys.items() if now - t < 30}
        if key in self.recent_keys:
            return True
        self.recent_keys[key] = now
        return False

    def get_order(self, client_order_id: str) -> PaperOrder | None:
        return self.open_orders.get(client_order_id) or self.orders_by_id.get(client_order_id)

    def list_open_orders(self) -> list[dict[str, Any]]:
        return [
            o.to_dict()
            for o in self.open_orders.values()
            if o.state
            in {
                PaperOrderState.SUBMITTED,
                PaperOrderState.ACKNOWLEDGED,
                PaperOrderState.PARTIALLY_FILLED,
                PaperOrderState.CANCEL_REQUESTED,
            }
        ]

    def _apply_fill(self, order: PaperOrder, qty: float, fill_price: float) -> None:
        if qty <= 0:
            return
        prev = order.filled_qty
        order.filled_qty = min(order.quantity, order.filled_qty + qty)
        filled_now = order.filled_qty - prev
        if filled_now <= 0:
            return
        if order.avg_fill_price is None:
            order.avg_fill_price = fill_price
        else:
            order.avg_fill_price = (
                (order.avg_fill_price * prev) + (fill_price * filled_now)
            ) / max(order.filled_qty, 1e-12)
        order.fills.append(
            {
                "qty": filled_now,
                "price": fill_price,
                "ts": utc_now().isoformat(),
                "pnl_type": "PAPER",
            }
        )
        dsk = parse_data_source_kind(self.data_source_kind).value
        if dsk in {"LIVE", "DELAYED", "BROKER"}:
            dsk = "SIMULATED"
        if order.side == "BUY":
            self.ledger.apply_buy(
                order.symbol,
                order.sector,
                filled_now,
                fill_price,
                f"{order.order_id}-F{len(order.fills)}",
                order.stop_price,
                order.target_price,
                data_source_kind=dsk,
            )
        else:
            self.ledger.apply_sell(
                order.symbol,
                filled_now,
                fill_price,
                f"{order.order_id}-F{len(order.fills)}",
                data_source_kind=dsk,
            )
        if order.filled_qty + 1e-12 >= order.quantity:
            order.state = PaperOrderState.FILLED
            self.open_orders.pop(order.client_order_id, None)
        else:
            order.state = PaperOrderState.PARTIALLY_FILLED
        order.updated_at = utc_now().isoformat()

    def submit(self, order: OrderRequest, sector: str) -> OrderResult:
        if settings.mode == "LIVE" and not bool(getattr(settings, "live_broker_enabled", False)):
            return OrderResult(False, None, "BLOCKED", "LIVE mode disabled — paper path only")
        if getattr(settings, "execution_mode", "PAPER").upper() == "LIVE" and not bool(
            getattr(settings, "live_broker_enabled", False)
        ):
            # Dry-run / confirmation gate: never treat paper broker as live venue
            pass
        if settings.kill_switch:
            return OrderResult(False, None, "BLOCKED", "KILL_SWITCH")

        # Market session gate (BIST)
        try:
            from data.integrity import MarketSession, bist_session_now

            if bist_session_now() == MarketSession.CLOSED and bool(
                getattr(settings, "block_orders_when_market_closed", True)
            ):
                # Allow paper/simulated after-hours only when explicitly permitted
                if not bool(getattr(settings, "allow_paper_when_closed", True)):
                    return OrderResult(False, None, "BLOCKED", "MARKET_CLOSED")
        except Exception:  # noqa: BLE001
            pass

        key = order.client_order_id or f"{order.side}:{order.symbol}:{order.quantity}:{round(order.price, 2)}"
        if order.client_order_id and order.client_order_id in self.open_orders:
            existing = self.open_orders[order.client_order_id]
            return OrderResult(
                False,
                existing.order_id,
                "DUPLICATE",
                "duplicate client_order_id — open order exists",
                details=existing.to_dict(),
            )
        if self._duplicate(key):
            return OrderResult(False, None, "DUPLICATE", "duplicate order protection")

        paper = PaperOrder(
            client_order_id=key,
            order_id=f"P-{uuid.uuid4().hex[:10]}",
            symbol=order.symbol,
            side=order.side,
            sector=sector,
            quantity=float(order.quantity),
            price=float(order.price),
            stop_price=order.stop_price,
            target_price=order.target_price,
            reason=order.reason,
            state=PaperOrderState.CREATED,
        )
        paper.state = PaperOrderState.VALIDATED
        paper.state = PaperOrderState.SUBMITTED
        paper.state = PaperOrderState.ACKNOWLEDGED
        self.open_orders[paper.client_order_id] = paper
        self.orders_by_id[paper.order_id] = paper

        slip = settings.slippage_pct + settings.commission_pct
        fill_px = order.price * (1 + slip) if order.side == "BUY" else order.price * (1 - slip)
        partial_pct = float(getattr(settings, "paper_partial_fill_pct", 1.0) or 1.0)
        partial_pct = min(1.0, max(0.0, partial_pct))
        fill_qty = paper.quantity * partial_pct

        try:
            self._apply_fill(paper, fill_qty, fill_px)
        except ValueError as exc:
            paper.state = PaperOrderState.REJECTED
            paper.updated_at = utc_now().isoformat()
            self.open_orders.pop(paper.client_order_id, None)
            return OrderResult(False, paper.order_id, "REJECTED", str(exc))

        status = paper.state.value
        return OrderResult(
            True,
            paper.order_id,
            status,
            f"paper {order.side.lower()} {status.lower()}",
            paper.avg_fill_price,
            paper.filled_qty,
            {
                "client_order_id": paper.client_order_id,
                "remaining": paper.remaining,
                "pnl_type": "PAPER",
                "order": paper.to_dict(),
            },
        )

    def cancel(self, client_order_id: str) -> OrderResult:
        order = self.open_orders.get(client_order_id) or self.orders_by_id.get(client_order_id)
        if order is None:
            return OrderResult(False, None, "FAILED", "order not found")
        if order.state in {PaperOrderState.FILLED, PaperOrderState.CANCELLED, PaperOrderState.REJECTED}:
            return OrderResult(False, order.order_id, order.state.value, "order already terminal")
        order.state = PaperOrderState.CANCEL_REQUESTED
        # Race: allow one more tiny partial before cancel settles (optional)
        if order.remaining > 0 and float(getattr(settings, "paper_cancel_race_fill_pct", 0.0) or 0) > 0:
            race = order.remaining * float(settings.paper_cancel_race_fill_pct)
            slip = settings.slippage_pct + settings.commission_pct
            px = order.price * (1 + slip) if order.side == "BUY" else order.price * (1 - slip)
            try:
                self._apply_fill(order, race, px)
            except ValueError:
                pass
        if order.state != PaperOrderState.FILLED:
            order.state = PaperOrderState.CANCELLED
            self.open_orders.pop(order.client_order_id, None)
        order.updated_at = utc_now().isoformat()
        return OrderResult(
            True,
            order.order_id,
            order.state.value,
            "cancel processed",
            order.avg_fill_price,
            order.filled_qty,
            order.to_dict(),
        )

    def fill_remaining(self, client_order_id: str) -> OrderResult:
        """Complete remaining quantity (paper)."""
        order = self.open_orders.get(client_order_id)
        if order is None:
            return OrderResult(False, None, "FAILED", "no open order")
        if order.remaining <= 0:
            return OrderResult(True, order.order_id, order.state.value, "nothing remaining")
        slip = settings.slippage_pct + settings.commission_pct
        px = order.price * (1 + slip) if order.side == "BUY" else order.price * (1 - slip)
        try:
            self._apply_fill(order, order.remaining, px)
        except ValueError as exc:
            return OrderResult(False, order.order_id, "REJECTED", str(exc))
        return OrderResult(
            True,
            order.order_id,
            order.state.value,
            "remaining filled",
            order.avg_fill_price,
            order.filled_qty,
            order.to_dict(),
        )
