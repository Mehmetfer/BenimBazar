"""Crypto trade plan — fractional position sizing (BIST size_from_risk uses int shares)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config.models import IndicatorSet, TradePlan
from config.settings import Settings, settings as default_settings
from trade_plan.engine import compute_stop, compute_targets


@dataclass
class CryptoTradePlanView:
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    risk_reward: float
    position_size: float
    max_risk_quote: float
    risk_per_unit: float
    stop_reason: str = ""
    market_type: str = "CRYPTO"

    def to_legacy(self) -> TradePlan:
        return TradePlan(
            entry=self.entry,
            stop=self.stop_loss,
            target1=self.target_1,
            target2=self.target_2,
            target3=self.target_3,
            risk_reward=self.risk_reward,
            quantity=self.position_size,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def crypto_size_from_risk(
    *,
    equity: float,
    entry: float,
    stop: float,
    size_mult: float = 1.0,
    max_exposure_pct: float = 15.0,
    cash: float | None = None,
    cfg: Settings | None = None,
) -> tuple[float, float, float]:
    """Fractional qty for crypto. Returns (qty, max_risk_quote, risk_per_unit)."""
    cfg = cfg or default_settings
    risk_pu = abs(entry - stop)
    if risk_pu <= 0 or entry <= 0 or equity <= 0:
        return 0.0, 0.0, 0.0
    max_risk = equity * (cfg.max_position_risk_pct / 100.0) * max(0.0, size_mult)
    qty = max_risk / risk_pu
    max_notional = equity * (max_exposure_pct / 100.0)
    if qty * entry > max_notional:
        qty = max_notional / entry
    if cash is not None and qty * entry > cash:
        qty = max(0.0, cash / entry)
    # round to 6 decimals for crypto
    qty = float(f"{qty:.6f}")
    return qty, round(max_risk, 2), round(risk_pu, 6)


def build_crypto_trade_plan(
    *,
    price: float,
    ind: IndicatorSet,
    equity: float,
    cash: float,
    size_mult: float = 1.0,
    max_exposure_pct: float = 15.0,
    side: str = "BUY",
    cfg: Settings | None = None,
) -> CryptoTradePlanView | None:
    cfg = cfg or default_settings
    if price <= 0 or ind.atr14 <= 0:
        return None
    stop, reason = compute_stop(price=price, ind=ind, side=side, cfg=cfg)
    t1, t2, t3, rr = compute_targets(entry=price, stop=stop, ind=ind, p_win=0.5, cfg=cfg)
    qty, max_risk, risk_pu = crypto_size_from_risk(
        equity=equity,
        entry=price,
        stop=stop,
        size_mult=size_mult,
        max_exposure_pct=max_exposure_pct,
        cash=cash,
        cfg=cfg,
    )
    return CryptoTradePlanView(
        entry=round(price, 6),
        stop_loss=round(stop, 6),
        target_1=round(t1.price, 6),
        target_2=round(t2.price, 6),
        target_3=round(t3.price, 6),
        risk_reward=round(rr, 2),
        position_size=qty,
        max_risk_quote=max_risk,
        risk_per_unit=risk_pu,
        stop_reason=reason,
    )
