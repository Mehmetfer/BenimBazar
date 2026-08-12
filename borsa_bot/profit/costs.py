"""Transaction-cost and edge-vs-cost helpers for NO_TRADE decisions.

Round-trip cost (BUY+SELL) must be beaten by expected_value before trading.
"""

from __future__ import annotations

from config.settings import Settings, settings as default_settings


def round_trip_cost_pct(cfg: Settings | None = None) -> float:
    """Commission + slippage both sides, as % of notional (e.g. 0.5 == 0.5%)."""
    cfg = cfg or default_settings
    # settings store fractions (0.002 = 0.2%); convert to percent points to match EV units
    one_way = (float(cfg.commission_pct) + float(cfg.slippage_pct)) * 100.0
    return round(2.0 * one_way, 4)


def net_expectancy_pct(gross_ev_pct: float, cfg: Settings | None = None) -> float:
    """Gross EV (% of entry) minus round-trip costs."""
    return round(float(gross_ev_pct) - round_trip_cost_pct(cfg), 4)


def edge_covers_cost(gross_ev_pct: float, cfg: Settings | None = None) -> bool:
    cfg = cfg or default_settings
    net = net_expectancy_pct(gross_ev_pct, cfg)
    floor = float(cfg.min_expected_value)
    # Must clear both configured floor and non-negative net after costs
    return net > max(floor, 0.0)


def edge_below_cost_reason(gross_ev_pct: float, cfg: Settings | None = None) -> str:
    cfg = cfg or default_settings
    cost = round_trip_cost_pct(cfg)
    net = net_expectancy_pct(gross_ev_pct, cfg)
    return (
        f"edge_below_cost: gross_ev={gross_ev_pct:.4f}% "
        f"round_trip_cost={cost:.4f}% net_ev={net:.4f}% "
        f"min_expected_value={cfg.min_expected_value}"
    )
