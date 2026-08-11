from __future__ import annotations

from dataclasses import asdict

from config.models import SignalAction


def risk_adjusted_opportunity_score(row: dict) -> float:
    """Rank by EV / risk / confidence — not raw ROI."""
    opp = row.get("opportunity") or {}
    scores = row.get("scores") or {}
    ev = float(opp.get("expected_value") or 0)
    conf = float(opp.get("confidence") or row.get("ai_confidence") or 50)
    risk = float(scores.get("risk") or 50)
    dd_imp = float(opp.get("drawdown_impact") or 1)
    p_win = float(opp.get("p_win") or 0.5)
    return round(ev * 12 + conf * 0.35 + p_win * 20 - risk * 0.4 - dd_imp * 5, 2)


def top_opportunities(universe: list[dict], *, n: int = 10) -> dict:
    buys = [u for u in universe if u.get("decision") in {"BUY", "STRONG_BUY", "AL"} or u.get("signal") == "AL"]
    watches = [u for u in universe if u.get("decision") in {"WATCH", "WAIT", "BEKLE"}]
    sells = [u for u in universe if u.get("decision") in {"SELL", "STRONG_SELL", "SAT"} or u.get("signal") == "SAT"]

    def rank(rows):
        scored = [{**r, "risk_adjusted_rank_score": risk_adjusted_opportunity_score(r)} for r in rows]
        scored.sort(key=lambda x: x["risk_adjusted_rank_score"], reverse=True)
        return scored[:n]

    return {
        "TOP_BUY": rank(buys),
        "TOP_WATCH": rank(watches),
        "TOP_SELL": rank(sells),
        "note": "Risk-adjusted ranking — not raw score chasing. Not investment advice.",
    }


def daily_market_report(dash: dict) -> dict:
    health = dash.get("health") or {}
    universe = dash.get("universe") or []
    if not universe:
        return {"empty": True}
    regime = universe[0].get("regime")
    # Sector leaders/laggards via sector score
    by_sector: dict[str, list[float]] = {}
    for u in universe:
        sc = (u.get("scores") or {}).get("sector")
        if sc is None:
            continue
        by_sector.setdefault(u.get("sector", "?"), []).append(sc)
    sector_avg = {k: sum(v) / len(v) for k, v in by_sector.items()}
    leaders = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)[:3]
    laggards = sorted(sector_avg.items(), key=lambda x: x[1])[:3]

    def top_factor(key: str, n: int = 5):
        rows = []
        for u in universe:
            factors = u.get("factors") or {}
            if key in factors:
                rows.append((u["symbol"], factors[key]))
            elif key in (u.get("scores") or {}):
                rows.append((u["symbol"], u["scores"][key]))
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows[:n]

    no_trade = [u["symbol"] for u in universe if u.get("decision") in {"NO_TRADE", "ALMA"}]
    return {
        "bist_regime": regime,
        "capital_mode": health.get("capital_mode"),
        "sector_leaders": leaders,
        "sector_laggards": laggards,
        "top_momentum": top_factor("momentum"),
        "top_relative_strength": top_factor("sector"),
        "top_value": top_factor("value"),
        "top_quality": top_factor("quality"),
        "high_risk": [u["symbol"] for u in universe if (u.get("scores") or {}).get("risk", 0) >= 55][:10],
        "no_trade_conditions": no_trade,
        "disclaimer": "Simulated/paper context. Past metrics ≠ future results. No profit guarantee.",
    }
