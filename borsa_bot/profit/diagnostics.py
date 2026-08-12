"""Loss attribution from paper ledger — evidence for profitability diagnostics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import settings
from profit.costs import round_trip_cost_pct


LOSS_CATEGORIES = (
    "SIGNAL_ERROR",
    "TIMING_ERROR",
    "EXECUTION_ERROR",
    "COST_ERROR",
    "STOP_ERROR",
    "TAKE_PROFIT_ERROR",
    "OVERTRADING",
    "DATA_ERROR",
    "OTHER",
)


@dataclass
class ClosedRound:
    symbol: str
    entry: float
    exit: float
    quantity: float
    pnl: float
    ret_pct: float
    entry_ts: str
    exit_ts: str
    hold_seconds: float
    category: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LossAttributionReport:
    trade_count_buys: int
    trade_count_sells: int
    closed_rounds: int
    winners: int
    losers: int
    win_rate: float
    realized_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    round_trip_cost_pct: float
    category_pnl: dict[str, float] = field(default_factory=dict)
    category_share_of_losses: dict[str, float] = field(default_factory=dict)
    rounds: list[ClosedRound] = field(default_factory=list)
    data_source_note: str = ""
    profitability_status: str = "PROFITABILITY_UNPROVEN"
    root_cause_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rounds"] = [r.to_dict() for r in self.rounds]
        return d


def _hold_seconds(a: str, b: str) -> float:
    try:
        from datetime import datetime

        ta = datetime.fromisoformat(a.replace("Z", "+00:00"))
        tb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return max(0.0, (tb - ta).total_seconds())
    except Exception:  # noqa: BLE001
        return 0.0


def _categorize(ret_pct: float, hold_s: float, pnl: float) -> tuple[str, str]:
    """Heuristic attribution from observable trade stats (not ML)."""
    cost = round_trip_cost_pct()
    if pnl >= 0:
        if hold_s < 180:
            return "TAKE_PROFIT_ERROR", "fast winner — verify if T1 full-exit caps edge"
        return "OTHER", "winner"
    # losers
    if hold_s < 180 and ret_pct <= -1.5:
        return "TIMING_ERROR", "stopped/exited within 3 minutes — noise or delayed fill"
    if abs(ret_pct) <= cost * 1.5 and hold_s < 600:
        return "COST_ERROR", "loss magnitude near round-trip cost band"
    if ret_pct <= -5.0:
        return "STOP_ERROR", "loss far beyond planned ~2% stop — gap/mark exit"
    if hold_s < 600:
        return "OVERTRADING", "short hold loser — auto-follow churn"
    if ret_pct <= -2.0:
        return "SIGNAL_ERROR", "stop-region loser — entry quality / regime"
    return "OTHER", "unclassified loser"


def analyze_paper_ledger(db_path: Path | None = None) -> LossAttributionReport:
    import sqlite3

    path = Path(db_path or settings.db_path)
    if not path.is_file():
        return LossAttributionReport(
            0,
            0,
            0,
            0,
            0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            round_trip_cost_pct(),
            root_cause_summary="paper.db missing",
            data_source_note="NO_DB",
        )

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    trades = con.execute(
        "SELECT id, ts, side, symbol, quantity, price, pnl FROM trades ORDER BY id"
    ).fetchall()
    con.close()

    buys = [t for t in trades if str(t["side"]).upper() == "BUY"]
    sells = [t for t in trades if str(t["side"]).upper() == "SELL"]
    buy_lots: dict[str, list[list[float | str]]] = defaultdict(list)
    rounds: list[ClosedRound] = []

    for t in trades:
        sym = str(t["symbol"])
        side = str(t["side"]).upper()
        qty = float(t["quantity"])
        px = float(t["price"])
        pnl = float(t["pnl"] or 0)
        ts = str(t["ts"] or "")
        if side == "BUY":
            buy_lots[sym].append([qty, px, ts])
            continue
        left = qty
        entry_cost = 0.0
        entry_qty = 0.0
        entry_ts = ""
        while left > 0 and buy_lots[sym]:
            lot = buy_lots[sym][0]
            take = min(left, float(lot[0]))
            entry_cost += take * float(lot[1])
            entry_qty += take
            entry_ts = entry_ts or str(lot[2])
            lot[0] = float(lot[0]) - take
            left -= take
            if float(lot[0]) <= 1e-9:
                buy_lots[sym].pop(0)
        avg_entry = (entry_cost / entry_qty) if entry_qty else px
        ret = (px / avg_entry - 1.0) * 100.0 if avg_entry else 0.0
        hold = _hold_seconds(entry_ts, ts)
        cat, note = _categorize(ret, hold, pnl)
        rounds.append(
            ClosedRound(
                symbol=sym,
                entry=round(avg_entry, 4),
                exit=round(px, 4),
                quantity=qty,
                pnl=round(pnl, 2),
                ret_pct=round(ret, 3),
                entry_ts=entry_ts,
                exit_ts=ts,
                hold_seconds=round(hold, 1),
                category=cat,
                notes=note,
            )
        )

    winners = [r for r in rounds if r.pnl > 0]
    losers = [r for r in rounds if r.pnl <= 0]
    realized = sum(r.pnl for r in rounds)
    avg_win = (sum(r.pnl for r in winners) / len(winners)) if winners else 0.0
    avg_loss = (sum(r.pnl for r in losers) / len(losers)) if losers else 0.0
    gross_win = sum(r.pnl for r in winners)
    gross_loss = abs(sum(r.pnl for r in losers))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    wr = (len(winners) / len(rounds)) if rounds else 0.0
    expectancy = (wr * avg_win) - ((1 - wr) * abs(avg_loss)) if rounds else 0.0

    cat_pnl: dict[str, float] = {c: 0.0 for c in LOSS_CATEGORIES}
    for r in rounds:
        cat_pnl[r.category] = round(cat_pnl.get(r.category, 0.0) + r.pnl, 2)

    loss_total = sum(r.pnl for r in losers)  # negative
    shares: dict[str, float] = {}
    if loss_total < 0:
        for c, v in cat_pnl.items():
            if v < 0:
                shares[c] = round(abs(v) / abs(loss_total) * 100.0, 1)

    # Rank loss sources
    loss_ranked = sorted(((c, v) for c, v in cat_pnl.items() if v < 0), key=lambda x: x[1])
    top = ", ".join(f"{c} {v:.0f} TL ({shares.get(c, 0):.0f}%)" for c, v in loss_ranked[:5])
    root = (
        f"Closed rounds={len(rounds)} realized={realized:.2f} TL PF={pf:.2f} "
        f"expectancy={expectancy:.2f}/trade. Top loss sources: {top or 'n/a'}. "
        f"Auto-follow on simulated data + short-hold stop-outs are primary suspects when DATA_PROVIDER=simulated."
    )

    status = "PROFITABILITY_UNPROVEN"
    if len(rounds) >= 30 and expectancy > 0 and pf >= 1.2:
        status = "PROFITABILITY_CANDIDATE_NEEDS_OOS"  # still not proven
    if realized < 0 or expectancy <= 0:
        status = "PROFITABILITY_UNPROVEN"

    return LossAttributionReport(
        trade_count_buys=len(buys),
        trade_count_sells=len(sells),
        closed_rounds=len(rounds),
        winners=len(winners),
        losers=len(losers),
        win_rate=round(wr * 100.0, 1),
        realized_pnl=round(realized, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(pf, 3),
        expectancy=round(expectancy, 2),
        round_trip_cost_pct=round_trip_cost_pct(),
        category_pnl=cat_pnl,
        category_share_of_losses=shares,
        rounds=rounds,
        data_source_note=f"ledger={path.name}",
        profitability_status=status,
        root_cause_summary=root,
    )
