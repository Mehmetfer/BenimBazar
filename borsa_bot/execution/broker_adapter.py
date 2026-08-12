"""Broker adapter boundary — LIVE path is fail-closed until a real adapter is unlocked.

Architecture:
  AutonomousTradingEngine → ExecutionRouter → PaperBroker | LiveBrokerAdapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from config.models import OrderRequest, OrderResult
from config.settings import settings
from execution.paper import PaperBroker


class BrokerAdapter(Protocol):
    name: str

    def submit(self, order: OrderRequest, sector: str) -> OrderResult: ...

    def get_order(self, client_order_id: str) -> OrderResult | None: ...

    def positions(self) -> list[dict]: ...

    def balances(self) -> dict: ...


@dataclass
class LiveBrokerDisabled:
    """Placeholder adapter — never sends real money orders."""

    name: str = "LiveBrokerDisabled"

    def submit(self, order: OrderRequest, sector: str) -> OrderResult:
        return OrderResult(
            False,
            None,
            "BLOCKED",
            "LIVE broker adapter not enabled — LIVE_BROKER_ENABLED=false or no adapter configured",
            details={"client_order_id": order.client_order_id, "live_trading": False},
        )

    def get_order(self, client_order_id: str) -> OrderResult | None:
        return OrderResult(False, None, "UNKNOWN", "no live broker — cannot query order", details={"client_order_id": client_order_id})

    def positions(self) -> list[dict]:
        return []

    def balances(self) -> dict:
        return {"available": None, "note": "LIVE broker disabled"}


@dataclass
class ExecutionRouter:
    """Routes orders by execution mode. SHADOW never reaches a broker."""

    paper: PaperBroker
    live: BrokerAdapter | None = None

    def __post_init__(self) -> None:
        if self.live is None:
            self.live = LiveBrokerDisabled()

    def submit(self, order: OrderRequest, sector: str, *, execution_mode: str) -> OrderResult:
        mode = (execution_mode or "PAPER").upper()
        if mode == "SHADOW":
            return OrderResult(
                True,
                None,
                "SHADOW",
                "WOULD submit — shadow mode does not send orders",
                order.price,
                order.quantity,
                {
                    "would": True,
                    "side": order.side,
                    "symbol": order.symbol,
                    "client_order_id": order.client_order_id,
                    "stop": order.stop_price,
                    "target": order.target_price,
                },
            )
        if mode == "LIVE":
            from trading_safety.live_gate import is_live_broker_enabled, is_live_confirmed

            if not is_live_broker_enabled():
                return OrderResult(False, None, "BLOCKED", "LIVE_BROKER_ENABLED=false")
            if bool(getattr(settings, "live_confirmation_required", True)) and not is_live_confirmed():
                return OrderResult(
                    False,
                    None,
                    "BLOCKED",
                    "LIVE_CONFIRMATION_REQUIRED — set LIVE_CONFIRMED=true after explicit human confirmation",
                )
            # Idempotency: never blind-retry — query first if client_order_id set
            if order.client_order_id:
                existing = self.live.get_order(order.client_order_id)
                if existing is not None and existing.status in {"FILLED", "PARTIALLY_FILLED", "ACKNOWLEDGED", "SUBMITTED"}:
                    return existing
            return self.live.submit(order, sector)
        # PAPER
        return self.paper.submit(order, sector)


def build_execution_router(paper: PaperBroker) -> ExecutionRouter:
    """Factory helper — live side always resolved via live_factory (default disabled)."""
    from execution.live_factory import resolve_live_adapter

    return ExecutionRouter(paper=paper, live=resolve_live_adapter())

