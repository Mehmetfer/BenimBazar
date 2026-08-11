from __future__ import annotations

from config.models import FundamentalSnapshot

# Simulated fundamentals for paper MVP — marked available=True but clearly synthetic.
# Real KAP/FinTables adapters should replace this provider.

_FAKE: dict[str, dict] = {
    "THYAO": {"pe": 6.5, "pb": 1.1, "roe": 0.28, "roa": 0.09, "net_margin": 0.14, "debt_equity": 0.9, "revenue_growth": 0.18, "earnings_growth": 0.22, "current_ratio": 1.2, "dividend_yield": 0.01},
    "ASELS": {"pe": 22.0, "pb": 4.5, "roe": 0.18, "roa": 0.08, "net_margin": 0.16, "debt_equity": 0.3, "revenue_growth": 0.25, "earnings_growth": 0.2, "current_ratio": 1.8, "dividend_yield": 0.005},
    "GARAN": {"pe": 5.2, "pb": 0.9, "roe": 0.32, "roa": 0.03, "net_margin": 0.35, "debt_equity": 0.0, "revenue_growth": 0.12, "earnings_growth": 0.1, "current_ratio": 1.0, "dividend_yield": 0.04},
    "EREGL": {"pe": 8.0, "pb": 0.8, "roe": 0.12, "roa": 0.06, "net_margin": 0.1, "debt_equity": 0.5, "revenue_growth": 0.05, "earnings_growth": -0.02, "current_ratio": 1.4, "dividend_yield": 0.03},
    "BIMAS": {"pe": 18.0, "pb": 5.0, "roe": 0.35, "roa": 0.12, "net_margin": 0.04, "debt_equity": 0.4, "revenue_growth": 0.2, "earnings_growth": 0.15, "current_ratio": 0.9, "dividend_yield": 0.02},
}


def get_fundamentals(symbol: str) -> FundamentalSnapshot:
    raw = _FAKE.get(symbol)
    if not raw:
        return FundamentalSnapshot(symbol=symbol, available=False)
    return FundamentalSnapshot(symbol=symbol, available=True, **raw)


def score_fundamentals(f: FundamentalSnapshot) -> tuple[float, list[str]]:
    if not f.available:
        return 50.0, ["fundamental_data_unavailable_neutral"]
    score = 50.0
    notes: list[str] = []
    # Quality
    if (f.roe or 0) >= 0.15:
        score += 10
        notes.append("roe_quality")
    if (f.net_margin or 0) >= 0.08:
        score += 6
    # Growth
    if (f.revenue_growth or 0) >= 0.1:
        score += 8
        notes.append("revenue_growth")
    if (f.earnings_growth or 0) < 0:
        score -= 8
        notes.append("earnings_contraction")
    # Valuation (context, not binary cheap/expensive)
    pe = f.pe or 15
    if 4 <= pe <= 12:
        score += 8
        notes.append("reasonable_pe")
    elif pe > 25:
        score -= 6
        notes.append("rich_valuation")
    # Financial risk
    if (f.debt_equity or 0) > 1.5:
        score -= 10
        notes.append("high_leverage")
    if (f.current_ratio or 1) < 1:
        score -= 5
        notes.append("liquidity_pressure")
    return max(0.0, min(100.0, score)), notes
