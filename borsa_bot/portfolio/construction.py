from __future__ import annotations

from dataclasses import dataclass

from config.models import CapitalMode, MarketRegime, OpportunityMetrics
from config.settings import Settings, settings as default_settings


@dataclass
class PortfolioTarget:
    symbol: str
    sector: str
    side: str  # BUY/FLAT/SELL
    quantity: float
    risk_budget_tl: float
    weight: float
    reason: str


def correlation_proxy(returns_a: list[float], returns_b: list[float]) -> float:
    n = min(len(returns_a), len(returns_b))
    if n < 5:
        return 0.0
    a = returns_a[-n:]
    b = returns_b[-n:]
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
    sa = (sum((x - ma) ** 2 for x in a) / n) ** 0.5
    sb = (sum((y - mb) ** 2 for y in b) / n) ** 0.5
    if sa == 0 or sb == 0:
        return 0.0
    return max(-1.0, min(1.0, cov / (sa * sb)))


def build_correlation_matrix(series: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    symbols = list(series.keys())
    out: dict[str, dict[str, float]] = {}
    for i, s1 in enumerate(symbols):
        out[s1] = {}
        for s2 in symbols:
            out[s1][s2] = round(correlation_proxy(series[s1], series[s2]), 3) if s1 != s2 else 1.0
    return out


def sector_concentration_penalty(sector_count: int, max_sector: int) -> float:
    if sector_count >= max_sector:
        return 0.0
    if sector_count == max_sector - 1:
        return 0.5
    return 1.0


def size_position(
    *,
    equity: float,
    price: float,
    stop: float,
    opp: OpportunityMetrics | None,
    capital_mode: CapitalMode,
    regime: MarketRegime,
    sector_count: int,
    corr_with_book: float,
    cfg: Settings | None = None,
) -> PortfolioTarget | None:
    cfg = cfg or default_settings
    if price <= 0 or stop >= price or stop <= 0:
        return None
    risk_ps = price - stop
    risk_budget = equity * (cfg.max_position_risk_pct / 100.0)
    mult = opp.position_size_mult if opp else 0.5
    if capital_mode == CapitalMode.DEFENSIVE:
        mult *= 0.5
    elif capital_mode == CapitalMode.HIGH_RISK:
        mult *= 0.35
    elif capital_mode in {CapitalMode.CAPITAL_PROTECTION, CapitalMode.KILL_SWITCH}:
        return None
    if regime == MarketRegime.BEAR:
        mult *= 0.6
    if regime == MarketRegime.STRONG_BEAR:
        return None
    mult *= sector_concentration_penalty(sector_count, cfg.max_sector_positions)
    if corr_with_book >= 0.75:
        mult *= 0.4  # correlated book penalty
    elif corr_with_book >= 0.5:
        mult *= 0.7
    risk_budget *= max(0.0, mult)
    if risk_budget <= 0:
        return None
    qty = int(risk_budget / risk_ps)
    if qty <= 0:
        return None
    notional = qty * price
    weight = notional / equity if equity else 0
    return PortfolioTarget(
        symbol="",
        sector="",
        side="BUY",
        quantity=float(qty),
        risk_budget_tl=round(risk_budget, 2),
        weight=round(weight, 4),
        reason=f"risk_based size_mult={mult:.2f} corr={corr_with_book:.2f}",
    )
