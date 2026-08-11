from __future__ import annotations

from alerts.events import AlertEventType, AlertPriority, TradingAlertEvent
from alerts.manager import AlertManager
from config.models import SymbolDecision
from favorites.store import FavoritesStore


def emit_favorite_signal_alerts(
    manager: AlertManager,
    store: FavoritesStore,
    decisions: list[SymbolDecision],
    *,
    favorite_voice: bool = True,
) -> None:
    """Favorite-specific alerts. Does not change trading decisions."""
    fav_syms = store.symbols()
    if not fav_syms:
        return
    for d in decisions:
        if d.symbol not in fav_syms:
            continue
        fav = store.get(d.symbol)
        ai = getattr(d, "ai_trade_plan", None)
        decision = d.decision.value if d.decision else d.signal.value
        prev = store.update_last_signal(d.symbol, decision, d.ai_confidence)

        # AI direction change alerts
        if prev and prev != decision:
            change_kind = _change_kind(prev, decision)
            store.add_event(
                d.symbol,
                "AI_SIGNAL_CHANGE",
                f"{prev} → {decision}",
                {"prev": prev, "new": decision},
            )
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.BUY_SIGNAL
                    if "GÜÇLENDİ" in change_kind or "BUY" in decision
                    else AlertEventType.SELL_SIGNAL,
                    symbol=d.symbol,
                    priority=AlertPriority.HIGH,
                    confidence=d.ai_confidence,
                    title=f"★ FAVORİ — {change_kind}",
                    message=f"FAVORİ HİSSE AI: {d.symbol} {prev} → {decision}. {change_kind}",
                    tts_text=f"Favori hisseniz {d.symbol} için yapay zeka sinyali değişti. {prev} den {decision} a.",
                    payload={"favorite": True, "change": change_kind, "prev": prev, "new": decision},
                    dedupe_key=f"FAV_AI_CHANGE:{d.symbol}:{prev}:{decision}",
                )
            )

        actionable = decision in {
            "STRONG_BUY",
            "BUY",
            "SELL",
            "STRONG_SELL",
            "AL",
            "SAT",
            "WAIT_FOR_ENTRY",
        }
        pa = d.price_action or {}
        breakout = bool(pa.get("false_breakout") is False and (pa.get("pattern") or "").upper().find("BREAK") >= 0)
        if not actionable and not breakout:
            continue

        zone = ""
        stop = d.stop_price
        t1 = t2 = t3 = None
        rr = None
        if ai is not None:
            zone = f"{ai.entry_zone.low}–{ai.entry_zone.high}"
            stop = ai.stop_loss
            t1, t2, t3 = ai.target1.price, ai.target2.price, ai.target3.price
            rr = ai.risk_reward

        title = f"★ FAVORİ SİNYALİ — {d.symbol}"
        msg = (
            f"★ FAVORİ SİNYALİ\n"
            f"{d.symbol}\n"
            f"{decision}\n"
            f"Giriş: {zone or '—'} TL\n"
            f"Stop: {stop if stop is not None else '—'} TL\n"
            f"Hedef: {t1 or '—'} / {t2 or '—'} / {t3 or '—'} TL\n"
            f"Confidence: {int(d.ai_confidence)}\n"
            f"R/R: 1:{rr if rr is not None else '—'}\n"
            f"FAVORİ HİSSENDE SİNYAL OLUŞTU. Favori ≠ otomatik AL."
        )
        tts = (
            f"Favori hisseniz {d.symbol} için {decision.replace('_', ' ').lower()} sinyali oluştu."
        )
        if ai is not None and favorite_voice:
            tts = (
                f"Favori hisseniz {d.symbol} için güçlü al sinyali oluştu. "
                f"Önerilen giriş {ai.entry_zone.low} ile {ai.entry_zone.high} lira arasında."
                if decision in {"STRONG_BUY", "BUY", "AL"}
                else tts
            )
        prio = AlertPriority.HIGH
        if decision in {"STRONG_BUY", "STRONG_SELL"} or decision in {"AL", "SAT"} and d.ai_confidence >= 85:
            prio = AlertPriority.CRITICAL if decision in {"STRONG_BUY", "STRONG_SELL"} else AlertPriority.HIGH

        store.add_event(d.symbol, "FAVORITE_SIGNAL", msg, {"decision": decision})
        manager.publish(
            TradingAlertEvent(
                event_type=AlertEventType.BUY_SIGNAL
                if decision in {"STRONG_BUY", "BUY", "AL", "WAIT_FOR_ENTRY"}
                else AlertEventType.SELL_SIGNAL,
                symbol=d.symbol,
                priority=prio,
                price=d.price,
                confidence=d.ai_confidence,
                risk_reward=rr,
                stop=stop,
                target=t1,
                title=title,
                message=msg,
                tts_text=tts if favorite_voice else None,
                strategy=(ai.strategy if ai else None),
                payload={
                    "favorite": True,
                    "push_body": msg,
                    "sms_ascii": f"FAV {decision} {d.symbol} | SL {stop} | TP {t1} | Conf {int(d.ai_confidence)}"[:160],
                },
                dedupe_key=f"FAV_SIGNAL:{d.symbol}:{decision}",
            )
        )


def check_favorite_price_alerts(
    manager: AlertManager,
    store: FavoritesStore,
    marks: dict[str, float],
    plans: dict[str, object] | None = None,
) -> list[str]:
    fired: list[str] = []
    plans = plans or {}
    for rule in store.list_price_alerts():
        px = marks.get(rule.symbol)
        if px is None:
            continue
        hit = False
        detail = ""
        if rule.kind == "ABOVE" and rule.threshold is not None and px >= rule.threshold:
            hit, detail = True, f"{rule.symbol} > {rule.threshold}"
        elif rule.kind == "BELOW" and rule.threshold is not None and px <= rule.threshold:
            hit, detail = True, f"{rule.symbol} < {rule.threshold}"
        elif rule.kind in {"STOP", "TARGET", "ENTRY_ZONE"}:
            plan = plans.get(rule.symbol)
            if plan is None:
                continue
            if rule.kind == "STOP" and getattr(plan, "stop_loss", None) and px <= plan.stop_loss:
                hit, detail = True, f"{rule.symbol} stop bölgesi"
            if rule.kind == "TARGET" and getattr(plan, "target1", None) and px >= plan.target1.price:
                hit, detail = True, f"{rule.symbol} hedef 1"
            if rule.kind == "ENTRY_ZONE" and getattr(plan, "entry_zone", None):
                z = plan.entry_zone
                if z.low <= px <= z.high:
                    hit, detail = True, f"{rule.symbol} giriş bölgesinde"
        if hit:
            fired.append(detail)
            store.add_event(rule.symbol, "PRICE_ALERT", detail, {"kind": rule.kind, "price": px})
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.WATCH_SIGNAL,
                    symbol=rule.symbol,
                    priority=AlertPriority.HIGH,
                    price=px,
                    title=f"★ FAVORİ FİYAT ALARMI — {rule.symbol}",
                    message=f"FAVORİ FİYAT ALARMI: {detail} (fiyat={px})",
                    tts_text=f"Favori hisseniz {rule.symbol} için fiyat alarmı. {detail}",
                    payload={"favorite": True, "price_alert": True},
                    dedupe_key=f"FAV_PX:{rule.alert_id}:{round(px,2)}",
                )
            )
    return fired


def _change_kind(prev: str, new: str) -> str:
    order = {
        "NO_TRADE": 0,
        "ALMA": 0,
        "WAIT": 1,
        "BEKLE": 1,
        "WATCH": 2,
        "WAIT_FOR_ENTRY": 3,
        "BUY": 4,
        "AL": 4,
        "STRONG_BUY": 5,
        "SELL": 4,
        "SAT": 4,
        "STRONG_SELL": 5,
    }
    # Direction flip
    buys = {"BUY", "STRONG_BUY", "AL", "WAIT_FOR_ENTRY"}
    sells = {"SELL", "STRONG_SELL", "SAT"}
    if prev in buys and new in sells or prev in sells and new in buys:
        return "FAVORİ HİSSEDE YÖN DEĞİŞTİ"
    po, no = order.get(prev, 2), order.get(new, 2)
    if no > po and new in buys | {"WATCH", "WAIT_FOR_ENTRY"}:
        return "FAVORİ HİSSE AI SİNYALİ GÜÇLENDİ"
    if no < po:
        return "FAVORİ HİSSEDE SİNYAL ZAYIFLADI"
    return "FAVORİ HİSSE AI GÜNCELLENDİ"
