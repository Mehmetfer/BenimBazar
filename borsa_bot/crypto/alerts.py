"""Crypto signal → AlertManager bridge (reuse sound/push/TTS/SMS — no live orders)."""

from __future__ import annotations

from typing import Any

from alerts.events import AlertEventType, AlertPriority, TradingAlertEvent
from alerts.manager import AlertManager
from favorites.store import FavoritesStore


_BUY = {"STRONG_BUY", "BUY", "AL"}
_SELL = {"STRONG_SELL", "SELL", "SAT"}
_ACTIONABLE = _BUY | _SELL


def emit_crypto_signal_alerts(
    manager: AlertManager,
    rows: list[dict[str, Any]],
    *,
    favorites: FavoritesStore | None = None,
) -> int:
    """Publish crypto SIGNAL / RISK alerts. Never emits ORDER_* (no execution).

    Supported kinds: STRONG BUY, BUY, SELL, STOP, TARGET, RISK.
    """
    emitted = 0
    fav_syms = favorites.symbols(market_type="CRYPTO") if favorites else set()

    for row in rows:
        signal = str(row.get("signal") or row.get("decision") or "").upper()
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        score = float(row.get("model_score") or row.get("confidence") or 0)
        price = row.get("price")
        plan = row.get("trade_plan") or {}
        risk = row.get("risk") or {}
        entry = row.get("entry") if row.get("entry") is not None else plan.get("entry")
        stop = row.get("stop") if row.get("stop") is not None else plan.get("stop_loss")
        target = row.get("target")
        if target is None:
            target = plan.get("target_1")
        rr = row.get("risk_reward")
        if rr is None:
            rr = plan.get("risk_reward")
        is_fav = bool(row.get("is_favorite")) or symbol in fav_syms
        fav_prefix = "★ CRYPTO " if is_fav else "CRYPTO "

        # RISK gate alerts
        if isinstance(risk, dict) and risk.get("allowed") is False:
            reason = str(risk.get("reason") or risk.get("verdict") or "risk block")
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.RISK_ALERT,
                    symbol=symbol,
                    priority=AlertPriority.CRITICAL,
                    price=price if isinstance(price, (int, float)) else None,
                    confidence=score,
                    message=f"{fav_prefix}RİSK: {symbol} — {reason}",
                    tts_text=f"Kripto risk alarmı. {symbol}.",
                    payload={
                        "market_type": "CRYPTO",
                        "signal": signal,
                        "risk": risk,
                        "favorite": is_fav,
                        "paper_only": True,
                    },
                    dedupe_key=f"CRYPTO_RISK:{symbol}:{reason}",
                )
            )
            emitted += 1

        if signal not in _ACTIONABLE:
            # Favorite direction tracking still updates store
            if favorites and is_fav:
                favorites.update_last_signal(symbol, signal, score, market_type="CRYPTO")
            continue

        # Skip weak BUY noise (same spirit as BIST bridge) except STRONG_BUY / favorites
        if signal in _BUY and signal != "STRONG_BUY" and score < 70 and not is_fav:
            continue

        if signal in _BUY:
            et = AlertEventType.BUY_SIGNAL
            title = f"{fav_prefix}{'GÜÇLÜ AL' if signal == 'STRONG_BUY' else 'AL'} — {symbol}"
            msg = (
                f"{title}. Fiyat {price}. Giriş {entry} · Stop {stop} · Hedef {target} · R/R {rr}. "
                f"Model skoru {score}. Paper only — canlı emir yok."
            )
            tts = f"Kripto al sinyali. {symbol}."
        else:
            et = AlertEventType.SELL_SIGNAL
            title = f"{fav_prefix}{'GÜÇLÜ SAT' if signal == 'STRONG_SELL' else 'SAT'} — {symbol}"
            msg = f"{title}. Fiyat {price}. Model skoru {score}. Paper only."
            tts = f"Kripto sat sinyali. {symbol}."

        manager.publish(
            TradingAlertEvent(
                event_type=et,
                symbol=symbol,
                strategy="crypto",
                price=price if isinstance(price, (int, float)) else None,
                confidence=score,
                risk_reward=float(rr) if rr is not None else None,
                stop=float(stop) if stop is not None else None,
                target=float(target) if target is not None else None,
                title=title,
                message=msg,
                tts_text=tts,
                payload={
                    "market_type": "CRYPTO",
                    "signal": signal,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "favorite": is_fav,
                    "paper_only": True,
                    "live_trading": False,
                },
                dedupe_key=f"CRYPTO_{et.value}:{symbol}:{signal}",
            )
        )
        emitted += 1

        # Explicit STOP / TARGET informational (plan levels — not fills)
        if stop is not None and signal in _BUY:
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.WATCH_SIGNAL,
                    symbol=symbol,
                    priority=AlertPriority.NORMAL,
                    price=float(stop),
                    title=f"{fav_prefix}STOP plan — {symbol}",
                    message=f"CRYPTO STOP seviyesi (plan): {symbol} @ {stop}. Emir değil.",
                    payload={"market_type": "CRYPTO", "kind": "STOP", "paper_only": True},
                    dedupe_key=f"CRYPTO_STOP_PLAN:{symbol}:{stop}",
                )
            )
            emitted += 1
        if target is not None and signal in _BUY:
            manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.WATCH_SIGNAL,
                    symbol=symbol,
                    priority=AlertPriority.NORMAL,
                    price=float(target),
                    title=f"{fav_prefix}TARGET plan — {symbol}",
                    message=f"CRYPTO TARGET seviyesi (plan): {symbol} @ {target}. Emir değil.",
                    payload={"market_type": "CRYPTO", "kind": "TARGET", "paper_only": True},
                    dedupe_key=f"CRYPTO_TARGET_PLAN:{symbol}:{target}",
                )
            )
            emitted += 1

        if favorites and is_fav:
            prev = favorites.update_last_signal(symbol, signal, score, market_type="CRYPTO")
            if prev and prev != signal:
                favorites.add_event(
                    symbol,
                    "AI_SIGNAL_CHANGE",
                    f"{prev} → {signal}",
                    {"prev": prev, "new": signal, "market_type": "CRYPTO"},
                    market_type="CRYPTO",
                )

    return emitted
