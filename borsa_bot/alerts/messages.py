from __future__ import annotations

from alerts.events import AlertEventType, TradingAlertEvent


def _num_tr(n: float | None, digits: int = 2) -> str:
    if n is None:
        return "—"
    return f"{n:.{digits}f}".replace(".", ",")


def _confidence_words(c: float | None) -> str:
    if c is None:
        return "bilinmiyor"
    # Simple Turkish TTS-friendly integer words for common scores
    n = int(round(c))
    return str(n)  # keep numeric for clarity; TTS engines read digits in TR


def format_alert(event: TradingAlertEvent) -> TradingAlertEvent:
    """Fill title/message/tts if empty using Turkish templates."""
    sym = event.symbol or "—"
    conf = event.confidence
    rr = event.risk_reward
    price = event.price
    stop = event.stop
    target = event.target
    strategy = event.strategy or event.payload.get("strategy") or "—"

    if event.event_type == AlertEventType.BUY_SIGNAL:
        # Prefer full trade-plan message if already set by bridge
        if not event.message:
            event.title = event.title or f"GÜÇLÜ AL — {sym}"
            event.message = (
                f"HİSSE AL SİNYALİ: {sym}. Güven skoru {int(conf) if conf is not None else '—'}. "
                f"Risk/ödül 1’e {_num_tr(rr, 1)}. Modelin mevcut verilere göre tahmini; garanti değildir."
            )
        event.title = event.title or f"GÜÇLÜ AL — {sym}"
        if not event.tts_text:
            event.tts_text = (
                f"{sym} için güçlü al sinyali oluştu. Güven skoru {_confidence_words(conf)}. "
                f"Bu modelin mevcut verilere göre tahminidir."
            )
        event.payload.setdefault(
            "push_body",
            event.payload.get("push_body")
            or _push_body(sym, price, conf, rr, stop, target, strategy, "AL"),
        )

    elif event.event_type == AlertEventType.SELL_SIGNAL:
        event.title = event.title or f"SAT — {sym}"
        reason = event.payload.get("reason") or "Trend zayıfladı. Risk seviyesi yükseldi."
        event.message = event.message or f"SAT SİNYALİ: {sym}. {reason}"
        event.tts_text = event.tts_text or f"{sym} için sat sinyali oluştu."
        event.payload.setdefault("push_body", _push_body(sym, price, conf, rr, stop, target, strategy, "SAT"))

    elif event.event_type == AlertEventType.STOP_LOSS:
        event.title = event.title or f"STOP LOSS — {sym}"
        event.message = event.message or f"STOP LOSS GERÇEKLEŞTİ. {sym} pozisyonu kapatıldı."
        event.tts_text = event.tts_text or f"{sym} stop loss gerçekleşti."

    elif event.event_type == AlertEventType.TAKE_PROFIT:
        level = event.payload.get("tp_level") or 1
        event.title = event.title or f"TAKE PROFIT — {sym}"
        event.message = event.message or f"TAKE PROFIT GERÇEKLEŞTİ. {sym} hedef {level}’e ulaştı."
        event.tts_text = event.tts_text or f"{sym} take profit gerçekleşti."

    elif event.event_type == AlertEventType.TRAILING_STOP:
        event.title = event.title or f"TRAILING STOP — {sym}"
        event.message = event.message or "TRAILING STOP GERÇEKLEŞTİ."
        event.tts_text = event.tts_text or f"{sym} trailing stop gerçekleşti."

    elif event.event_type == AlertEventType.KILL_SWITCH:
        event.title = event.title or "KRİTİK: KILL SWITCH"
        event.message = event.message or "KRİTİK: Trading sistemi yeni emirleri durdurdu."
        event.tts_text = event.tts_text or "Kritik. Trading sistemi yeni emirleri durdurdu."

    elif event.event_type == AlertEventType.RISK_ALERT:
        detail = event.payload.get("detail") or event.message or "Risk limiti aşıldı."
        event.title = event.title or "RİSK ALARMI"
        event.message = event.message or f"RİSK ALARMI: {detail}"
        event.tts_text = event.tts_text or "Portföy risk limiti aşıldı."

    elif event.event_type == AlertEventType.ORDER_REJECTED:
        event.title = event.title or f"EMİR REDDEDİLDİ — {sym}"
        why = event.payload.get("reason") or event.message or "Bilinmeyen neden"
        event.message = event.message or f"ORDER_REJECTED: {sym}. {why}"
        event.tts_text = event.tts_text or f"{sym} emri reddedildi."

    elif event.event_type == AlertEventType.ORDER_FILLED:
        side = event.payload.get("side") or ""
        event.title = event.title or f"EMİR DOLDU — {sym}"
        event.message = event.message or (
            f"ORDER_FILLED: {sym} {side} @ {_num_tr(price)} "
            f"(SIGNAL ≠ EXECUTION — bu bir dolum bildirimidir)."
        )
        event.tts_text = event.tts_text or f"{sym} emri doldu."

    elif event.event_type == AlertEventType.DAILY_SUMMARY:
        event.title = event.title or "GÜNLÜK TRADING RAPORU"
        event.message = event.message or _daily_message(event.payload)
        event.tts_text = event.tts_text or "Günlük trading raporu hazır."

    elif event.event_type in {
        AlertEventType.ORDER_SUBMITTED,
        AlertEventType.ORDER_ACCEPTED,
        AlertEventType.ORDER_PARTIAL,
        AlertEventType.ORDER_CANCELLED,
    }:
        event.title = event.title or f"{event.event_type.value} — {sym}"
        event.message = event.message or f"{event.event_type.value}: {sym}"
        event.tts_text = event.tts_text or f"{sym} emir durumu {event.event_type.value}."

    elif event.event_type in {AlertEventType.DATA_FEED_FAILURE, AlertEventType.BROKER_API_FAILURE}:
        event.title = event.title or f"KRİTİK: {event.event_type.value}"
        event.message = event.message or f"KRİTİK ALARM: {event.event_type.value}"
        event.tts_text = event.tts_text or "Kritik sistem arızası. Veri veya broker bağlantısı."

    else:
        event.title = event.title or event.event_type.value
        event.message = event.message or event.title
        event.tts_text = event.tts_text or event.message

    return event


def _push_body(
    sym: str,
    price: float | None,
    conf: float | None,
    rr: float | None,
    stop: float | None,
    target: float | None,
    strategy: str,
    side: str,
) -> str:
    return (
        f"{side} — {sym}\n"
        f"Fiyat: {_num_tr(price)} TL\n"
        f"Confidence: {int(conf) if conf is not None else '—'}/100\n"
        f"R/R: {_num_tr(rr, 1)}\n"
        f"Stop: {_num_tr(stop)}\n"
        f"Target: {_num_tr(target)}\n"
        f"Strategy: {strategy}"
    )


def _daily_message(payload: dict) -> str:
    return (
        "GÜNLÜK TRADING RAPORU\n"
        f"Toplam işlem: {payload.get('total_trades', '—')}\n"
        f"Kazanan: {payload.get('winners', '—')}\n"
        f"Kaybeden: {payload.get('losers', '—')}\n"
        f"Win rate: {payload.get('win_rate', '—')}\n"
        f"Realized P&L: {payload.get('realized_pnl', '—')}\n"
        f"Unrealized P&L: {payload.get('unrealized_pnl', '—')}\n"
        f"Drawdown: {payload.get('drawdown_pct', '—')}\n"
        f"En iyi: {payload.get('best_trade', '—')}\n"
        f"En kötü: {payload.get('worst_trade', '—')}\n"
        f"Aktif pozisyon: {payload.get('open_positions', '—')}\n"
        f"Risk seviyesi: {payload.get('risk_level', '—')}"
    )
