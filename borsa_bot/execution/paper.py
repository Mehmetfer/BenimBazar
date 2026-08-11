from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from config.models import OrderRequest, OrderResult
from config.settings import settings
from data.provenance import parse_data_source_kind
from portfolio.ledger import PortfolioLedger


@dataclass
class PaperBroker:
    ledger: PortfolioLedger
    recent_keys: dict[str, float] = field(default_factory=dict)
    data_source_kind: str = "SIMULATED"  # paper path — never claim LIVE

    def _duplicate(self, key: str) -> bool:
        now = time.time()
        # purge old
        self.recent_keys = {k: t for k, t in self.recent_keys.items() if now - t < 30}
        if key in self.recent_keys:
            return True
        self.recent_keys[key] = now
        return False

    def submit(self, order: OrderRequest, sector: str) -> OrderResult:
        if settings.mode == "LIVE":
            return OrderResult(False, None, "BLOCKED", "LIVE mode disabled in MVP")
        if settings.kill_switch:
            return OrderResult(False, None, "BLOCKED", "KILL_SWITCH")

        key = order.client_order_id or f"{order.side}:{order.symbol}:{order.quantity}:{round(order.price,2)}"
        if self._duplicate(key):
            return OrderResult(False, None, "DUPLICATE", "duplicate order protection")

        # Client cannot override source via order.details — backend stamps paper as SIMULATED
        dsk = parse_data_source_kind(self.data_source_kind).value
        if dsk in {"LIVE", "DELAYED", "BROKER"}:
            dsk = "SIMULATED"

        slip = settings.slippage_pct + settings.commission_pct
        if order.side == "BUY":
            fill = order.price * (1 + slip)
            order_id = f"P-{uuid.uuid4().hex[:10]}"
            try:
                self.ledger.apply_buy(
                    order.symbol,
                    sector,
                    order.quantity,
                    fill,
                    order_id,
                    order.stop_price,
                    order.target_price,
                    data_source_kind=dsk,
                )
            except ValueError as exc:
                return OrderResult(False, None, "REJECTED", str(exc))
            return OrderResult(True, order_id, "FILLED", "paper buy filled", fill, order.quantity)

        fill = order.price * (1 - slip)
        order_id = f"P-{uuid.uuid4().hex[:10]}"
        try:
            pnl = self.ledger.apply_sell(
                order.symbol, order.quantity, fill, order_id, data_source_kind=dsk
            )
        except ValueError as exc:
            return OrderResult(False, None, "REJECTED", str(exc))
        return OrderResult(True, order_id, "FILLED", f"paper sell filled pnl={pnl:.2f}", fill, order.quantity, {"pnl": pnl})
