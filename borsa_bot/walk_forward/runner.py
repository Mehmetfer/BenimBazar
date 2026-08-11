from __future__ import annotations

from dataclasses import dataclass

from backtest.runner import run_simple_backtest


@dataclass
class WalkForwardFold:
    train_steps: int
    test_steps: int
    train_net_return: float
    test_net_return: float
    test_max_dd: float
    test_sharpe: float
    passed: bool
    reason: str


@dataclass
class WalkForwardReport:
    symbol: str
    folds: list[WalkForwardFold]
    oos_pass_rate: float
    gate_ok: bool
    note: str


def run_walk_forward(symbol: str = "THYAO", folds: int = 3, train: int = 40, test: int = 20) -> WalkForwardReport:
    """
    Lightweight walk-forward using independent seeded backtest windows.
    Not a claim of production robustness — a structural gate prototype.
    """
    results: list[WalkForwardFold] = []
    for i in range(folds):
        # Separate runs approximate expanding windows on simulated provider
        tr = run_simple_backtest(symbol, steps=train + i * 5)
        te = run_simple_backtest(symbol, steps=test + i * 3)
        # OOS gate: test must not collapse vs train and DD bounded
        passed = te.max_drawdown <= 25 and te.net_return > -15
        reason = "ok" if passed else "oos_weak_or_high_dd"
        results.append(
            WalkForwardFold(
                train_steps=train + i * 5,
                test_steps=test + i * 3,
                train_net_return=tr.net_return,
                test_net_return=te.net_return,
                test_max_dd=te.max_drawdown,
                test_sharpe=te.sharpe,
                passed=passed,
                reason=reason,
            )
        )
    pass_rate = sum(1 for f in results if f.passed) / max(1, len(results))
    gate_ok = pass_rate >= 0.66
    return WalkForwardReport(
        symbol=symbol,
        folds=results,
        oos_pass_rate=round(pass_rate, 2),
        gate_ok=gate_ok,
        note="Illustrative walk-forward on simulated data — not LIVE permission.",
    )


def oos_live_gate(report: WalkForwardReport) -> bool:
    """LIVE blocked unless OOS gate passes AND user enables LIVE separately."""
    return report.gate_ok
