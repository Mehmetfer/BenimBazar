"""Pre-trade gates — SIGNAL never becomes an order without all gates PASS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config.models import SignalAction, utc_now
from config.settings import settings
from data.integrity import MarketSession, bist_session_now


ENTRY_OK = {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}


@dataclass
class GateResult:
    name: str
    passed: bool
    reason: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreTradeGateResult:
    passed: bool
    gates: list[GateResult] = field(default_factory=list)
    reason: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "gates": [g.to_dict() for g in self.gates],
        }


def evaluate_pretrade_gates(
    trading: Any,
    decision: Any,
    *,
    signal_age_sec: float | None = None,
    max_signal_age_sec: float | None = None,
) -> PreTradeGateResult:
    """DATA → SIGNAL → TRADE_PLAN → RISK → POSITION → EXECUTION."""
    gates: list[GateResult] = []
    max_age = max_signal_age_sec if max_signal_age_sec is not None else float(settings.signal_ttl_sec)

    # DATA GATE
    try:
        meta = trading.provider.source_meta(settings.data_freshness_sec)
        kind = meta.kind.value if hasattr(meta.kind, "value") else str(meta.kind)
        fresh_ok = trading.provider.is_fresh(settings.data_freshness_sec) or kind == "SIMULATED"
        if settings.is_production and kind in {"SIMULATED", "MOCK", "UNKNOWN"}:
            gates.append(GateResult("DATA", False, "PRODUCTION_MOCK_BLOCK", {"kind": kind}))
        elif kind in {"UNKNOWN", "MOCK"}:
            gates.append(GateResult("DATA", False, f"DATA_KIND_{kind}", {"kind": kind}))
        elif not trading.provider.has_market_data():
            gates.append(GateResult("DATA", False, "NO_MARKET_DATA"))
        elif not fresh_ok:
            gates.append(GateResult("DATA", False, "STALE_DATA", {"kind": kind}))
        else:
            quote = trading.provider.get_quote(decision.symbol)
            if not quote.price or quote.price <= 0:
                gates.append(GateResult("DATA", False, "MISSING_PRICE"))
            else:
                gates.append(
                    GateResult(
                        "DATA",
                        True,
                        "ok",
                        {"kind": kind, "price": quote.price, "spread_pct": quote.spread_pct},
                    )
                )
    except Exception as exc:  # noqa: BLE001
        gates.append(GateResult("DATA", False, f"DATA_ERROR:{exc}"))

    # SIGNAL GATE
    decision_v = getattr(decision, "decision", None) or getattr(decision, "signal", None)
    signal_v = getattr(decision, "signal", None)
    final = str(getattr(decision, "final_decision", "") or "")
    if decision_v not in ENTRY_OK and signal_v not in ENTRY_OK:
        gates.append(GateResult("SIGNAL", False, f"NOT_ENTRY:{decision_v}"))
    elif final.upper() in {"NO_TRADE", "WAIT", "WATCH", "ALMA", "BEKLE"}:
        gates.append(GateResult("SIGNAL", False, f"FINAL_{final}"))
    else:
        gates.append(
            GateResult(
                "SIGNAL",
                True,
                "ok",
                {
                    "decision": getattr(decision_v, "value", str(decision_v)),
                    "model_score": getattr(decision, "ai_confidence", None),
                    "calibrated_probability": None,
                    "note": "model_score ≠ calibrated probability",
                },
            )
        )

    # TRADE PLAN GATE
    plan = getattr(decision, "ai_trade_plan", None) or getattr(decision, "trade_plan", None)
    stop = getattr(decision, "stop_price", None)
    target = getattr(decision, "target_price", None)
    if plan is None and (stop is None or target is None):
        gates.append(GateResult("TRADE_PLAN", False, "MISSING_TRADE_PLAN"))
    else:
        gates.append(
            GateResult(
                "TRADE_PLAN",
                True,
                "ok",
                {"stop": stop, "target": target, "has_ai_plan": bool(getattr(decision, "ai_trade_plan", None))},
            )
        )

    # RISK GATE (soft read of prior verdict + kill/pause; sizing rechecked at execution)
    risk_verdict = str(getattr(decision, "risk_verdict", "") or "").upper()
    if settings.kill_switch:
        gates.append(GateResult("RISK", False, "KILL_SWITCH"))
    elif trading.risk.paused:
        gates.append(GateResult("RISK", False, f"PAUSED:{trading.risk.pause_reason}"))
    elif risk_verdict in {"REJECT", "BLOCKED"}:
        gates.append(GateResult("RISK", False, risk_verdict))
    else:
        gates.append(GateResult("RISK", True, "ok", {"risk_verdict": risk_verdict or "PASS"}))

    # POSITION GATE — duplicate open position
    if trading.ledger.get_position(decision.symbol) is not None:
        gates.append(GateResult("POSITION", False, "DUPLICATE_POSITION"))
    elif trading.ledger.open_position_count() >= settings.max_open_positions:
        gates.append(GateResult("POSITION", False, "MAX_OPEN_POSITIONS"))
    else:
        gates.append(GateResult("POSITION", True, "ok"))

    # EXECUTION GATE — signal age + safety snapshot + market session
    age = signal_age_sec if signal_age_sec is not None else 0.0
    if age > max_age:
        gates.append(GateResult("EXECUTION", False, "SIGNAL_STALE", {"age_sec": age, "max": max_age}))
    else:
        try:
            session = bist_session_now()
            if (
                session == MarketSession.CLOSED
                and bool(getattr(settings, "block_orders_when_market_closed", True))
                and not bool(getattr(settings, "allow_paper_when_closed", True))
            ):
                gates.append(GateResult("EXECUTION", False, "MARKET_CLOSED", {"session": session.value}))
            else:
                quote = trading.provider.get_quote(decision.symbol)
                ok, reason = trading.safety.evaluate(
                    data_fresh=trading.provider.is_fresh(settings.data_freshness_sec)
                    or (trading.provider.source_meta(settings.data_freshness_sec).kind.value == "SIMULATED"),
                    api_ok=True,
                    order_status_ok=True,
                    spread_pct=float(quote.spread_pct or 0),
                    daily_loss_pct=trading.ledger.daily_loss_pct(),
                    clock_ok=True,
                    max_spread_pct=settings.max_spread_pct,
                )
                if not ok:
                    gates.append(GateResult("EXECUTION", False, reason))
                else:
                    gates.append(
                        GateResult(
                            "EXECUTION",
                            True,
                            "ok",
                            {
                                "checked_at": utc_now().isoformat(),
                                "spread_pct": quote.spread_pct,
                                "market_session": session.value,
                            },
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            gates.append(GateResult("EXECUTION", False, f"EXEC_ERROR:{exc}"))

    failed = next((g for g in gates if not g.passed), None)
    if failed:
        return PreTradeGateResult(False, gates, reason=f"{failed.name}:{failed.reason}")
    return PreTradeGateResult(True, gates, reason="ok")
