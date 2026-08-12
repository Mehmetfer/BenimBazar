"""Institutional desk gate for autonomous AUTO entries.

SIGNAL ≠ ORDER. Desk consensus must PASS before AUTO paper fills.
Uses FinalDecisionPipeline on the existing scan row (no extra Yahoo scan).
"""

from __future__ import annotations

from typing import Any

from desk.engine import _row_from_decision
from desk.pipeline import FinalDecisionPipeline

_BUY = frozenset({"BUY", "STRONG_BUY", "AL"})
_ENTRY_BUY = frozenset({"BUY"})


def _portfolio_snapshot(trading: Any) -> dict[str, Any]:
    try:
        snap = trading.paper_wallet()
        return {
            "open_positions": snap.get("open_positions") or len(snap.get("positions") or []),
            "max_open_positions": snap.get("max_open_positions") or 99,
            "exposure_pct": snap.get("exposure_pct") or 0,
            "daily_loss_pct": trading.ledger.daily_loss_pct(),
            "drawdown_pct": snap.get("drawdown_pct") or trading.ledger.drawdown_pct(),
            "cash": snap.get("cash"),
            "equity": snap.get("equity"),
        }
    except Exception:  # noqa: BLE001
        return {"open_positions": 0, "max_open_positions": 99}


def _data_context(trading: Any, row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("data_source_kind") or "UNKNOWN").upper()
    try:
        from config.settings import settings

        meta = trading.provider.source_meta(settings.data_freshness_sec)
        md = meta.to_dict() if hasattr(meta, "to_dict") else {}
        kind = str(md.get("data_source_kind") or md.get("kind") or kind).upper()
        connected = bool(md.get("connected", True))
        fresh = str(md.get("freshness") or "").upper() not in {"STALE", "EXPIRED"}
        return {
            "data_valid": connected and kind not in {"UNAVAILABLE", "UNKNOWN", "REQUIRED"},
            "data_fresh": fresh,
            "data_kind": kind,
            "index_bullish": None,
        }
    except Exception:  # noqa: BLE001
        # Row-only path (tests / offline): treat DELAYED/LIVE/SIM as usable
        usable = kind in {"DELAYED", "LIVE", "SIMULATED", "TEST", "BACKTEST"}
        return {
            "data_valid": usable,
            "data_fresh": usable,
            "data_kind": kind,
            "index_bullish": None,
        }


def evaluate_desk_gate(
    trading: Any,
    decision: Any,
    ser: dict[str, Any] | None = None,
    *,
    require_buy: bool = True,
) -> dict[str, Any]:
    """Run institutional desk pipeline on one candidate.

    Returns dict with allowed/veto/decision/entry_action/confidence/reason/desk.
    Fail-closed on errors when require_buy=True.
    """
    symbol = getattr(decision, "symbol", None) or (ser or {}).get("symbol") or ""
    row = ser if isinstance(ser, dict) and ser else None
    if row is None and decision is not None and not isinstance(decision, dict):
        try:
            row = _row_from_decision(decision)
        except Exception:  # noqa: BLE001
            row = {"symbol": symbol, "final_decision": "NO_TRADE", "scores": {}, "opportunity": {}}
    if not isinstance(row, dict):
        row = {"symbol": symbol, "final_decision": "NO_TRADE", "scores": {}, "opportunity": {}}

    try:
        pipeline = FinalDecisionPipeline()
        context = _data_context(trading, row)
        portfolio = _portfolio_snapshot(trading)
        regime = {"primary": str(row.get("regime") or "UNKNOWN")}
        result = pipeline.run(
            row,
            trading=trading,
            context=context,
            portfolio=portfolio,
            debate={},
            regime=regime,
        )
        consensus = result.get("consensus") or {}
        entry = result.get("entry") or {}
        final = str(result.get("final_decision") or consensus.get("decision") or "NO_TRADE").upper()
        entry_action = str(entry.get("action") or "NO_TRADE").upper()
        veto = bool(consensus.get("veto"))
        confidence = float(consensus.get("confidence") or 0)
        info = {
            "symbol": str(symbol).upper(),
            "decision": final,
            "entry_action": entry_action,
            "confidence": confidence,
            "veto": veto,
            "veto_reason": consensus.get("veto_reason") or "",
            "stages": result.get("stages") or [],
            "committee_votes": result.get("committee_votes") or [],
        }
    except Exception as exc:  # noqa: BLE001 — fail-closed for AUTO
        return {
            "allowed": False,
            "veto": True,
            "decision": "NO_TRADE",
            "entry_action": "NO_TRADE",
            "confidence": 0.0,
            "reason": f"DESK_ERROR:{exc}",
            "desk": None,
            "fail_closed": True,
        }

    if veto:
        allowed = False
        reason = str(consensus.get("veto_reason") or "DESK_VETO")
    elif require_buy:
        allowed = final in _BUY and entry_action in _ENTRY_BUY
        reason = "DESK_PASS" if allowed else f"DESK_BLOCK decision={final} entry={entry_action}"
    else:
        allowed = not veto
        reason = "DESK_OBSERVE"

    return {
        "allowed": allowed,
        "veto": veto,
        "decision": final,
        "entry_action": entry_action,
        "confidence": confidence,
        "reason": reason,
        "desk": info,
        "fail_closed": False,
    }
