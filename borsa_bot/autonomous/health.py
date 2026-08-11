"""Pre-start health check — fail-closed autonomous mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config.settings import settings


@dataclass
class HealthCheckResult:
    ok: bool
    blocked: bool
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_health_check(trading: Any, *, execution_mode: str = "PAPER") -> HealthCheckResult:
    """Check DATABASE, DATA PROVIDER, BROKER, ACCOUNT, MARKET, RISK, NOTIFICATIONS, PREDICTIONS."""
    checks: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    warnings: list[str] = []

    # Database / ledger
    try:
        eq = float(trading.ledger.equity())
        cash = float(trading.ledger.cash)
        checks["database"] = {"ok": True, "equity": eq, "cash": cash}
        if eq <= 0:
            failures.append("DATABASE_EQUITY_INVALID")
            checks["database"]["ok"] = False
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": str(exc)}
        failures.append("DATABASE_FAILURE")

    # Data provider
    try:
        meta = trading.provider.source_meta(settings.data_freshness_sec)
        has = bool(trading.provider.has_market_data())
        kind = getattr(meta, "kind", None)
        kind_v = kind.value if hasattr(kind, "value") else str(kind)
        fresh = bool(getattr(meta, "is_live_market", False) or str(getattr(meta, "freshness", "")).endswith("SIMULATED") or meta.freshness.value in {"FRESH", "FRESH_SIMULATED"})
        checks["data_provider"] = {
            "ok": has,
            "kind": kind_v,
            "fresh": fresh,
            "connected": bool(getattr(meta, "connected", has)),
        }
        if not has:
            failures.append("DATA_PROVIDER_FAILURE")
        if settings.is_production and kind_v in {"SIMULATED", "MOCK", "UNKNOWN"}:
            failures.append("PRODUCTION_MOCK_BLOCK")
            checks["data_provider"]["ok"] = False
        if execution_mode.upper() == "LIVE" and kind_v in {"SIMULATED", "MOCK", "UNKNOWN", "STUB"}:
            failures.append("LIVE_REQUIRES_REAL_DATA")
            checks["data_provider"]["ok"] = False
        if not fresh and has:
            warnings.append("DATA_STALE_OR_DEGRADED")
    except Exception as exc:  # noqa: BLE001
        checks["data_provider"] = {"ok": False, "error": str(exc)}
        failures.append("DATA_PROVIDER_FAILURE")

    # Broker
    live_enabled = bool(getattr(settings, "live_broker_enabled", False))
    checks["broker"] = {
        "ok": True,
        "paper": True,
        "live_broker_enabled": live_enabled,
        "live_adapter": "DISABLED" if not live_enabled else "PENDING",
    }
    if execution_mode.upper() == "LIVE" and not live_enabled:
        failures.append("LIVE_BROKER_DISABLED")
        checks["broker"]["ok"] = False

    # Account
    try:
        checks["account"] = {
            "ok": True,
            "equity": float(trading.ledger.equity()),
            "cash": float(trading.ledger.cash),
            "open_positions": int(trading.ledger.open_position_count()),
        }
    except Exception as exc:  # noqa: BLE001
        checks["account"] = {"ok": False, "error": str(exc)}
        failures.append("ACCOUNT_FAILURE")

    # Market / risk / notifications / predictions
    try:
        h = trading.health()
        checks["market_status"] = {
            "ok": h.get("status") not in {"KILL_SWITCH"} or True,
            "status": h.get("status"),
            "data_fresh": h.get("data_fresh"),
            "kill_switch": h.get("kill_switch"),
        }
        if h.get("kill_switch") or h.get("status") == "KILL_SWITCH":
            failures.append("KILL_SWITCH")
            checks["market_status"]["ok"] = False
        if h.get("paused"):
            warnings.append(f"RISK_PAUSED:{h.get('status')}")
    except Exception as exc:  # noqa: BLE001
        checks["market_status"] = {"ok": False, "error": str(exc)}
        failures.append("MARKET_STATUS_FAILURE")

    try:
        trading.risk.refresh_pause_state()
        checks["risk_engine"] = {
            "ok": not trading.risk.paused and not settings.kill_switch,
            "paused": trading.risk.paused,
            "pause_reason": trading.risk.pause_reason,
        }
        if settings.kill_switch:
            failures.append("KILL_SWITCH")
    except Exception as exc:  # noqa: BLE001
        checks["risk_engine"] = {"ok": False, "error": str(exc)}
        failures.append("RISK_ENGINE_FAILURE")

    try:
        _ = trading.alerts.settings_store.get()
        checks["notifications"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["notifications"] = {"ok": False, "error": str(exc)}
        warnings.append("NOTIFICATION_DEGRADED")

    try:
        _ = trading.predictions.reliability_report()
        checks["prediction_tracking"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["prediction_tracking"] = {"ok": False, "error": str(exc)}
        warnings.append("PREDICTION_TRACKING_DEGRADED")

    blocked = bool(failures)
    return HealthCheckResult(ok=not blocked, blocked=blocked, checks=checks, failures=failures, warnings=warnings)
