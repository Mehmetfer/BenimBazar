"""Paper wallet snapshot for BIST simulation UI."""

from __future__ import annotations

from typing import Any

from dashboard.daily import SIGNAL_RANK
from portfolio.ledger import PortfolioLedger


def _decision_rank(decision: str) -> int:
    return SIGNAL_RANK.get((decision or "").upper(), 50)


def paper_wallet_snapshot(ledger: PortfolioLedger) -> dict[str, Any]:
    starting = ledger.starting_cash
    cash = ledger.cash
    equity = ledger.equity()
    total_pnl = equity - starting
    total_pnl_pct = (total_pnl / starting * 100.0) if starting > 0 else 0.0
    holdings = ledger.holdings_value()
    realized = ledger.realized_pnl()
    unrealized = round(holdings - sum(p.quantity * p.avg_cost for p in ledger.positions()), 2)

    positions: list[dict[str, Any]] = []
    for p in ledger.positions():
        mark = float(ledger.mark_prices.get(p.symbol, p.avg_cost))
        cost_basis = p.quantity * p.avg_cost
        market_value = p.quantity * mark
        unreal = market_value - cost_basis
        unreal_pct = (unreal / cost_basis * 100.0) if cost_basis > 0 else 0.0
        positions.append(
            {
                "symbol": p.symbol,
                "sector": p.sector,
                "quantity": p.quantity,
                "avg_cost": round(p.avg_cost, 2),
                "price": round(mark, 2),
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "unrealized_pnl": round(unreal, 2),
                "unrealized_pnl_pct": round(unreal_pct, 2),
                "stop_price": p.stop_price,
                "target_price": p.target_price,
            }
        )
    positions.sort(
        key=lambda row: (
            _decision_rank("HOLD"),
            -float(row.get("unrealized_pnl") or 0),
            str(row.get("symbol") or ""),
        )
    )

    return {
        "market": "BIST",
        "currency": "TRY",
        "mode": "PAPER",
        "live_trading": False,
        "starting_cash": round(starting, 2),
        "cash": round(cash, 2),
        "holdings_value": round(holdings, 2),
        "equity": round(equity, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "daily_pnl": round(ledger.daily_pnl(), 2),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": unrealized,
        "drawdown_pct": round(ledger.drawdown_pct(), 2),
        "open_position_count": ledger.open_position_count(),
        "trade_count": ledger.trade_count(),
        "positions": positions,
        "recent_trades": ledger.recent_trades(30),
        "note": "Simülasyon cüzdanı · önerilerden otomatik paper al/sat · gerçek para değil",
    }
