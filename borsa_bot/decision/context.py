"""Phase 1 — AI Context Engine: observe market/account/data without inventing gaps."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config.models import utc_now
from config.settings import settings
from data.integrity import DataSourceKind
from data.providers import classify_provider
from market_regime.engine import detect_regime


@dataclass
class ContextPack:
    """Structured observation snapshot for one AI cycle (BIST or CRYPTO plane)."""

    cycle_id: str
    market_type: str
    observed_at: str
    market_regime: str
    data_kind: str
    data_fresh: bool
    data_connected: bool
    provider_class: str
    market_session: str
    equity: float
    cash: float
    open_positions: int
    daily_pnl: float
    drawdown_pct: float
    risk_paused: bool
    kill_switch: bool
    capital_mode: str
    prediction_tier: str
    prediction_sample: int
    unknowns: list[str] = field(default_factory=list)
    note: str = "Missing fields stay UNKNOWN — never invented"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def data_valid(self) -> bool:
        if self.kill_switch:
            return False
        if not self.data_connected:
            return False
        if self.data_kind in {
            DataSourceKind.UNKNOWN.value,
            DataSourceKind.REQUIRED.value,
            DataSourceKind.UNAVAILABLE.value,
            "MOCK",
        }:
            return False
        if settings.is_production and self.data_kind in {
            DataSourceKind.SIMULATED.value,
            DataSourceKind.TEST.value,
        }:
            return False
        return True


def build_context_pack(
    trading: Any,
    *,
    cycle_id: str,
    market_type: str = "BIST",
) -> ContextPack:
    unknowns: list[str] = []
    try:
        meta = trading.provider.source_meta(settings.data_freshness_sec)
        data_kind = meta.kind.value if hasattr(meta.kind, "value") else str(meta.kind)
        data_fresh = bool(trading.provider.is_fresh(settings.data_freshness_sec)) or data_kind == "SIMULATED"
        data_connected = bool(trading.provider.has_market_data())
        session = meta.market_session.value if hasattr(meta.market_session, "value") else str(meta.market_session)
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"DATA_META:{exc}")
        data_kind, data_fresh, data_connected, session = "UNKNOWN", False, False, "UNKNOWN"

    try:
        regime = detect_regime(trading.provider)
        regime_s = regime.value if hasattr(regime, "value") else str(regime)
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"REGIME:{exc}")
        regime_s = "UNKNOWN"

    try:
        pred = trading.predictions.reliability_report()
        tier = str(getattr(pred, "sample_tier", None) or getattr(pred, "grade", "INSUFFICIENT"))
        sample = int(getattr(pred, "sample_size", 0) or 0)
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"PREDICTION:{exc}")
        tier, sample = "INSUFFICIENT", 0

    try:
        capital_mode = trading.capital_mode.value if hasattr(trading.capital_mode, "value") else str(trading.capital_mode)
    except Exception:  # noqa: BLE001
        capital_mode = "UNKNOWN"
        unknowns.append("CAPITAL_MODE")

    return ContextPack(
        cycle_id=cycle_id,
        market_type=market_type.upper(),
        observed_at=utc_now().isoformat(),
        market_regime=regime_s,
        data_kind=data_kind,
        data_fresh=data_fresh,
        data_connected=data_connected,
        provider_class=classify_provider(trading.provider),
        market_session=session,
        equity=float(trading.ledger.equity()),
        cash=float(trading.ledger.cash),
        open_positions=int(trading.ledger.open_position_count()),
        daily_pnl=float(trading.ledger.daily_pnl()),
        drawdown_pct=float(trading.ledger.drawdown_pct()),
        risk_paused=bool(trading.risk.paused),
        kill_switch=bool(settings.kill_switch),
        capital_mode=capital_mode,
        prediction_tier=tier,
        prediction_sample=sample,
        unknowns=unknowns,
    )
