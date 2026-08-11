from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class StressResult:
    scenario: str
    pnl: float
    pnl_pct: float


@dataclass
class PortfolioRiskStats:
    var_95: float
    cvar_95: float
    stress: list[StressResult]
    note: str


def approximate_var_cvar(returns: list[float], equity: float, alpha: float = 0.95) -> tuple[float, float]:
    """Historical VaR/CVaR on return series (fraction). Not a guarantee."""
    if len(returns) < 10:
        return 0.0, 0.0
    ordered = sorted(returns)
    idx = max(0, int((1 - alpha) * len(ordered)) - 1)
    var_r = ordered[idx]
    tail = ordered[: idx + 1] or [var_r]
    cvar_r = sum(tail) / len(tail)
    return round(-var_r * equity, 2), round(-cvar_r * equity, 2)


def stress_test_portfolio(
    positions: list[dict],
    *,
    equity: float,
    beta_default: float = 1.0,
) -> list[StressResult]:
    """
    positions: {symbol, sector, value, beta?}
    Scenarios applied linearly — illustrative stress, not full revaluation.
    """
    scenarios = [
        ("BIST_-5%", -0.05, None),
        ("BIST_-10%", -0.10, None),
        ("BIST_-20%", -0.20, None),
        ("BANKA_-10%", -0.10, "BANKA"),
        ("SINGLE_NAME_-15%", -0.15, "SINGLE"),
        ("VOL_SHOCK_PROXY", -0.08, None),
        ("SPREAD_LIQ_SHOCK", -0.03, None),
    ]
    out: list[StressResult] = []
    if not positions:
        return [StressResult(s, 0.0, 0.0) for s, _, _ in scenarios]
    total = sum(p["value"] for p in positions) or 1.0
    largest = max(positions, key=lambda p: p["value"])
    for name, shock, filt in scenarios:
        pnl = 0.0
        for p in positions:
            beta = float(p.get("beta", beta_default))
            if filt == "BANKA" and p.get("sector") != "BANKA":
                continue
            if filt == "SINGLE" and p["symbol"] != largest["symbol"]:
                continue
            if filt is None:
                pnl += p["value"] * shock * beta
            else:
                pnl += p["value"] * shock
        if name == "SPREAD_LIQ_SHOCK":
            pnl = -total * 0.03
        out.append(StressResult(name, round(pnl, 2), round(pnl / equity * 100 if equity else 0, 2)))
    return out


def portfolio_risk_report(positions: list[dict], returns: list[float], equity: float) -> PortfolioRiskStats:
    var95, cvar95 = approximate_var_cvar(returns, equity)
    return PortfolioRiskStats(
        var_95=var95,
        cvar_95=cvar95,
        stress=stress_test_portfolio(positions, equity=equity),
        note="VaR/CVaR/stress are approximations on available history — not predictions.",
    )
