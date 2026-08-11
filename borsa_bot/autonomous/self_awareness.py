"""Self-awareness snapshot — bot knows its own health/metrics (Master V2 §53)."""

from __future__ import annotations

from typing import Any

from autonomous.governors import evaluate_governors
from autonomous.levels import resolve_autonomy_level
from alerts.status import channel_status_report
from config.settings import settings
from data.providers import classify_provider
from universe.tradeable import universe_stats


def self_awareness(trading: Any, engine: Any) -> dict[str, Any]:
    um = engine.user_mode()
    em = engine.execution_mode()
    blocked = bool(getattr(engine, "_halted", False))
    level = resolve_autonomy_level(um, em, blocked=blocked)
    gov = evaluate_governors(
        daily_loss_pct=float(trading.ledger.daily_loss_pct()),
        drawdown_pct=float(trading.ledger.drawdown_pct()),
        kill_switch=bool(settings.kill_switch),
    )
    last = engine.status().get("last_cycle") or {}
    signals = last.get("signals") or {}
    try:
        pred = trading.predictions.reliability_report()
        pred_note = {
            "grade": getattr(pred, "grade", None),
            "sample_size": getattr(pred, "sample_size", 0),
            "sample_tier": getattr(pred, "sample_tier", None),
            "historical_accuracy_pct": getattr(pred, "historical_accuracy_pct", None),
            "note": "Historical accuracy ≠ current forecast probability",
        }
    except Exception as exc:  # noqa: BLE001
        pred_note = {"error": str(exc), "sample_tier": "INSUFFICIENT"}

    meta = trading.provider.source_meta(settings.data_freshness_sec)
    return {
        "autonomy_level": level.to_dict(),
        "autonomous_status": "BLOCKED" if blocked or not gov.new_trades_allowed else "ACTIVE",
        "blocked_reason": getattr(engine, "_halt_reason", None)
        or (None if gov.new_trades_allowed else gov.reason),
        "governor": gov.to_dict(),
        "market": {
            "session": meta.market_session.value if hasattr(meta.market_session, "value") else str(meta.market_session),
            "data_kind": meta.kind.value if hasattr(meta.kind, "value") else str(meta.kind),
            "freshness": meta.freshness.value if hasattr(meta.freshness, "value") else str(meta.freshness),
            "provider_class": classify_provider(trading.provider),
        },
        "account": {
            "equity": trading.ledger.equity(),
            "cash": trading.ledger.cash,
            "daily_pnl": trading.ledger.daily_pnl(),
            "drawdown_pct": trading.ledger.drawdown_pct(),
            "open_positions": trading.ledger.open_position_count(),
        },
        "cycle": {
            "signals": signals,
            "orders_submitted": last.get("orders_submitted"),
            "symbols_scanned": last.get("symbols_scanned"),
            "status": last.get("status"),
        },
        "universe": universe_stats(),
        "model": pred_note,
        "notifications": channel_status_report()["channels"],
        "live_broker": "DISABLED",
        "principles": [
            "No guaranteed profit",
            "confidence ≠ calibrated probability",
            "FAVORITE ≠ RISK BYPASS",
            "LOSS → never increase risk / martingale",
            "SIGNAL ≠ ORDER",
        ],
    }
