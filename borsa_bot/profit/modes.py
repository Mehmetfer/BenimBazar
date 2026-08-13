from __future__ import annotations

from config.models import CapitalMode, MarketRegime
from config.settings import Settings, settings as default_settings
from portfolio.ledger import PortfolioLedger


def select_capital_mode(
    ledger: PortfolioLedger,
    *,
    regime: MarketRegime,
    atr_index_pct: float,
    liquidity_ok: bool,
    force_defensive: bool = False,
    cfg: Settings | None = None,
) -> CapitalMode:
    """
    Auto mode from drawdown, regime, volatility, consecutive losses, liquidity.
    Priority: KILL > CAPITAL_PROTECTION > HIGH_RISK > DEFENSIVE > NORMAL
    """
    cfg = cfg or default_settings
    if cfg.kill_switch:
        return CapitalMode.KILL_SWITCH

    dd = ledger.drawdown_pct()
    losses = ledger.consecutive_losses()
    daily = ledger.daily_loss_pct()

    if dd >= cfg.max_drawdown_pct or daily <= -cfg.daily_max_loss_pct:
        return CapitalMode.KILL_SWITCH
    if (
        dd >= cfg.capital_protection_dd_pct
        or losses >= cfg.consecutive_loss_pause
        or regime == MarketRegime.STRONG_BEAR
        or atr_index_pct >= 5.0
        or not liquidity_ok
    ):
        return CapitalMode.CAPITAL_PROTECTION
    if dd >= cfg.high_risk_dd_pct or regime == MarketRegime.BEAR or atr_index_pct >= 4.0:
        return CapitalMode.HIGH_RISK
    if (
        dd >= cfg.defensive_dd_pct
        or losses >= cfg.consecutive_loss_reduce
        or atr_index_pct >= 3.2
        or force_defensive
    ):
        return CapitalMode.DEFENSIVE
    return CapitalMode.NORMAL


def mode_allows_new_entries(mode: CapitalMode) -> bool:
    return mode in {CapitalMode.NORMAL, CapitalMode.DEFENSIVE, CapitalMode.HIGH_RISK}
