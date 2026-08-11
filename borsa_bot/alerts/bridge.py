from __future__ import annotations

"""Helpers that translate trading outcomes into alert events.

SIGNAL ≠ EXECUTION — callers must emit the correct event type.
"""

from alerts.events import AlertEventType, AlertPriority, TradingAlertEvent
from alerts.manager import AlertManager
from config.models import OrderResult, SignalAction, SymbolDecision


def emit_signal_alerts(manager: AlertManager, decisions: list[SymbolDecision]) -> None:
    """Emit SIGNAL alerts only (not fills). Strong buy/sell only — with full trade plan if present."""
    for d in decisions:
        ai = getattr(d, "ai_trade_plan", None)
        if d.decision in {SignalAction.STRONG_BUY, SignalAction.BUY} or d.signal == SignalAction.AL:
            if d.ai_confidence < 70 and d.decision != SignalAction.STRONG_BUY:
                continue
            plan = d.trade_plan
            opp = d.opportunity
            payload = {"decision": d.decision.value, "signal": d.signal.value}
            msg = None
            tts = None
            if ai is not None:
                payload["ai_trade_plan"] = True
                payload["entry_zone"] = f"{ai.entry_zone.low}-{ai.entry_zone.high}"
                payload["targets"] = [ai.target1.price, ai.target2.price, ai.target3.price]
                payload["preferred_plan"] = ai.preferred_plan
                payload["state"] = ai.state.value
                payload["push_body"] = ai.push_body
                payload["sms_ascii"] = ai.sms_ascii
                msg = ai.message_tr
                tts = ai.tts_tr
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.BUY_SIGNAL,
                    symbol=d.symbol,
                    strategy=_strategy_label(d),
                    price=d.price,
                    confidence=d.ai_confidence,
                    risk_reward=(
                        ai.risk_reward
                        if ai
                        else (plan.risk_reward if plan else (opp.risk_reward if opp else None))
                    ),
                    stop=ai.stop_loss if ai else (d.stop_price or (plan.stop if plan else None)),
                    target=ai.target1.price if ai else (d.target_price or (plan.target1 if plan else None)),
                    message=msg or "",
                    tts_text=tts,
                    payload=payload,
                    dedupe_key=f"BUY_SIGNAL:{d.symbol}:{d.decision.value}",
                )
            )
        elif d.decision in {SignalAction.STRONG_SELL, SignalAction.SELL} or d.signal == SignalAction.SAT:
            payload = {
                "decision": d.decision.value,
                "signal": d.signal.value,
                "reason": "Trend zayıfladı. Risk seviyesi yükseldi.",
            }
            msg = None
            tts = None
            if ai is not None:
                payload["push_body"] = ai.push_body
                payload["sms_ascii"] = ai.sms_ascii
                msg = ai.message_tr
                tts = ai.tts_tr
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.SELL_SIGNAL,
                    symbol=d.symbol,
                    strategy=_strategy_label(d),
                    price=d.price,
                    confidence=d.ai_confidence,
                    stop=d.stop_price,
                    target=d.target_price,
                    message=msg or "",
                    tts_text=tts,
                    payload=payload,
                    dedupe_key=f"SELL_SIGNAL:{d.symbol}:{d.decision.value}",
                )
            )


def emit_order_lifecycle(
    manager: AlertManager,
    *,
    symbol: str,
    side: str,
    result: OrderResult,
    strategy: str | None = None,
    price: float | None = None,
) -> None:
    """Map paper/broker result → ORDER_* events (execution, not signal)."""
    status = (result.status or "").upper()
    mapping = {
        "SUBMITTED": AlertEventType.ORDER_SUBMITTED,
        "ACCEPTED": AlertEventType.ORDER_ACCEPTED,
        "PARTIAL": AlertEventType.ORDER_PARTIAL,
        "FILLED": AlertEventType.ORDER_FILLED,
        "CANCELLED": AlertEventType.ORDER_CANCELLED,
        "REJECTED": AlertEventType.ORDER_REJECTED,
        "BLOCKED": AlertEventType.ORDER_REJECTED,
        "DUPLICATE": AlertEventType.ORDER_REJECTED,
    }
    # Always emit submitted first for successful path
    if result.ok and status == "FILLED":
        manager.publish(
            TradingAlertEvent(
                event_type=AlertEventType.ORDER_SUBMITTED,
                symbol=symbol,
                price=price or result.fill_price,
                strategy=strategy,
                payload={"side": side, "order_id": result.order_id},
                dedupe_key=f"ORDER_SUBMITTED:{result.order_id}",
            )
        )
        manager.publish(
            TradingAlertEvent(
                event_type=AlertEventType.ORDER_FILLED,
                symbol=symbol,
                price=result.fill_price or price,
                strategy=strategy,
                payload={"side": side, "order_id": result.order_id, "qty": result.quantity},
                dedupe_key=f"ORDER_FILLED:{result.order_id}",
            )
        )
        return

    et = mapping.get(status, AlertEventType.ORDER_REJECTED if not result.ok else AlertEventType.ORDER_ACCEPTED)
    prio = AlertPriority.CRITICAL if et == AlertEventType.ORDER_REJECTED else None
    manager.publish(
        TradingAlertEvent(
            event_type=et,
            symbol=symbol,
            priority=prio,
            price=price or result.fill_price,
            strategy=strategy,
            payload={"side": side, "reason": result.message, "order_id": result.order_id, "status": status},
            dedupe_key=f"{et.value}:{symbol}:{result.order_id or result.message}",
        )
    )


def emit_risk_alert(manager: AlertManager, detail: str, *, symbol: str | None = None) -> None:
    manager.publish(
        TradingAlertEvent(
            event_type=AlertEventType.RISK_ALERT,
            symbol=symbol,
            priority=AlertPriority.CRITICAL,
            payload={"detail": detail},
            message=f"RİSK ALARMI: {detail}",
            dedupe_key=f"RISK_ALERT:{detail}",
        )
    )


def emit_kill_switch(manager: AlertManager) -> None:
    manager.publish(
        TradingAlertEvent(
            event_type=AlertEventType.KILL_SWITCH,
            priority=AlertPriority.CRITICAL,
            dedupe_key="KILL_SWITCH",
        )
    )


def emit_execution_exit(
    manager: AlertManager,
    *,
    symbol: str,
    kind: str,
    price: float | None = None,
    tp_level: int | None = None,
) -> None:
    """kind: STOP_LOSS | TAKE_PROFIT | TRAILING_STOP — only after real exit."""
    et = {
        "STOP_LOSS": AlertEventType.STOP_LOSS,
        "TAKE_PROFIT": AlertEventType.TAKE_PROFIT,
        "TRAILING_STOP": AlertEventType.TRAILING_STOP,
    }.get(kind.upper())
    if et is None:
        return
    manager.publish(
        TradingAlertEvent(
            event_type=et,
            symbol=symbol,
            price=price,
            payload={"tp_level": tp_level or 1},
            dedupe_key=f"{et.value}:{symbol}:{tp_level or ''}",
        )
    )


def emit_daily_summary(manager: AlertManager, payload: dict) -> None:
    manager.publish(
        TradingAlertEvent(
            event_type=AlertEventType.DAILY_SUMMARY,
            payload=payload,
            dedupe_key=f"DAILY_SUMMARY:{payload.get('date', 'today')}",
        )
    )


def _strategy_label(d: SymbolDecision) -> str:
    if d.alpha_summary and d.alpha_summary.get("label"):
        return str(d.alpha_summary.get("label"))
    votes = d.strategy_votes or {}
    if votes:
        return ",".join(list(votes.keys())[:2])
    return "ensemble"
