"""Professional daily briefing — regime, risk, opportunities, portfolio."""

from __future__ import annotations

from typing import Any

from analytics.post_trade import detect_model_drift
from desk.session import current_session_mode


def generate_daily_briefing(
    *,
    trading: Any,
    scan_rows: list[dict[str, Any]] | None = None,
    pipeline_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate desk-level morning/intraday/closing report from real scan data."""
    session = current_session_mode()
    wallet = {}
    try:
        wallet = trading.paper_wallet()
    except Exception:  # noqa: BLE001
        wallet = {}

    rows = scan_rows or []
    pipelines = pipeline_results or []

    buy_ops = [r for r in pipelines if r.get("final_decision") == "BUY"]
    wait_ops = [r for r in pipelines if r.get("final_decision") == "WAIT"]
    top = sorted(buy_ops, key=lambda x: float(x.get("signal_quality") or 0), reverse=True)[:5]

    regime = "UNKNOWN"
    if rows:
        regime = str(rows[0].get("regime") or "UNKNOWN")

    # Edge decay from recent paper trades if available
    edge_status = "UNVERIFIED"
    try:
        from profit.diagnostics import analyze_paper_ledger

        report = analyze_paper_ledger(trading.ledger.db_path)
        if report.trade_count_sells >= 5:
            decay = detect_model_drift(
                recent_hit_rate=report.win_rate / 100.0 if report.win_rate else 0.0,
                baseline_hit_rate=0.5,
                recent_avg_ev=report.expectancy,
            )
            edge_status = "DEGRADED" if decay.defensive else "STABLE"
    except Exception:  # noqa: BLE001
        pass

    sectors: dict[str, int] = {}
    for r in rows[:30]:
        sec = str(r.get("sector") or "OTHER")
        sectors[sec] = sectors.get(sec, 0) + 1

    return {
        "session_mode": session.value,
        "market_regime": regime,
        "market_risk": wallet.get("drawdown_pct"),
        "top_opportunities": [
            {
                "symbol": t.get("symbol"),
                "signal_quality": t.get("signal_quality"),
                "decision": t.get("final_decision"),
            }
            for t in top
        ],
        "wait_count": len(wait_ops),
        "buy_count": len(buy_ops),
        "scan_count": len(rows),
        "sector_strength": sectors,
        "current_positions": wallet.get("positions") or [],
        "portfolio_exposure": wallet.get("exposure_pct"),
        "cash": wallet.get("cash"),
        "equity": wallet.get("equity"),
        "edge_status": edge_status,
        "note": "Briefing from structured scan — not a profitability guarantee",
    }
