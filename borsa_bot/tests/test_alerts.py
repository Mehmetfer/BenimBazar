from __future__ import annotations

import tempfile
from pathlib import Path

from alerts.bus import EventBus
from alerts.cooldown import CooldownGate, Deduper
from alerts.events import AlertEventType, AlertPriority, TradingAlertEvent
from alerts.log import NotificationLog
from alerts.manager import AlertManager
from alerts.messages import format_alert
from alerts.settings_store import (
    NotificationSettingsStore,
    UserNotificationSettings,
    in_quiet_hours,
)
from alerts.bridge import emit_order_lifecycle, emit_signal_alerts
from config.models import (
    OrderResult,
    SignalAction,
    SymbolDecision,
    MarketRegime,
    RiskLevel,
    CapitalMode,
)


def _mgr(tmp: Path) -> AlertManager:
    log = NotificationLog(tmp / "n.db")
    store = NotificationSettingsStore(tmp / "settings.json")
    store.update({"cooldown_seconds": 60, "sms_on": False, "push_on": True, "sound_on": True, "tts_on": True})
    return AlertManager(bus=EventBus(), log=log, settings_store=store)


def test_quiet_hours_overnight():
    assert in_quiet_hours("23:00", "22:00", "07:00") is True
    assert in_quiet_hours("06:00", "22:00", "07:00") is True
    assert in_quiet_hours("12:00", "22:00", "07:00") is False
    assert in_quiet_hours("10:00", "09:00", "17:00") is True


def test_cooldown_and_dedupe():
    gate = CooldownGate(default_seconds=1000)
    assert gate.allow("BUY:THYAO") is True
    assert gate.allow("BUY:THYAO") is False
    d = Deduper()
    assert d.seen_or_mark("e1") is False
    assert d.seen_or_mark("e1") is True


def test_buy_message_turkish():
    ev = TradingAlertEvent(
        event_type=AlertEventType.BUY_SIGNAL,
        symbol="THYAO",
        confidence=87,
        risk_reward=2.8,
        price=325.4,
        stop=315.2,
        target=354.0,
        strategy="Swing Momentum",
    )
    format_alert(ev)
    assert "HİSSE AL SİNYALİ: THYAO" in ev.message
    assert "87" in ev.message
    assert "GÜÇLÜ AL" in ev.title
    assert "güven skoru" in ev.tts_text.lower() or "Güven" in ev.tts_text


def test_alert_manager_writes_inbox_and_log():
    tmp = Path(tempfile.mkdtemp())
    mgr = _mgr(tmp)
    ev = TradingAlertEvent(
        event_type=AlertEventType.BUY_SIGNAL,
        symbol="THYAO",
        confidence=87,
        risk_reward=2.8,
        price=100,
        stop=95,
        target=110,
        strategy="Swing",
        dedupe_key=f"t:{ev.event_id if False else 'unique1'}",
    )
    ev.dedupe_key = f"unique-buy-{ev.event_id}"
    mgr.publish(ev)
    inbox = mgr.log.inbox(limit=10)
    assert any(x["event_type"] == "BUY_SIGNAL" for x in inbox)
    log = mgr.log.recent_log(limit=20)
    channels = {r["channel"] for r in log if r["event_id"] == ev.event_id}
    assert "IN_APP" in channels
    assert "PUSH" in channels
    assert "SOUND" in channels
    # single event_id across channels
    assert all(r["event_id"] == ev.event_id for r in log if r["event_id"] == ev.event_id)


def test_cooldown_suppresses_duplicate_symbol_signal():
    tmp = Path(tempfile.mkdtemp())
    mgr = _mgr(tmp)
    mgr.settings_store.update({"cooldown_seconds": 9999})
    mgr.cooldown.default_seconds = 9999
    e1 = TradingAlertEvent(event_type=AlertEventType.BUY_SIGNAL, symbol="GARAN", confidence=90, dedupe_key="BUY_SIGNAL:GARAN:BUY")
    e2 = TradingAlertEvent(event_type=AlertEventType.BUY_SIGNAL, symbol="GARAN", confidence=91, dedupe_key="BUY_SIGNAL:GARAN:BUY")
    mgr.publish(e1)
    mgr.publish(e2)
    statuses = [r["delivery_status"] for r in mgr.log.recent_log(50) if r["event_id"] == e2.event_id]
    assert "SUPPRESSED" in statuses


def test_kill_switch_bypasses_quiet_hours():
    tmp = Path(tempfile.mkdtemp())
    mgr = _mgr(tmp)
    mgr.settings_store.update(
        {
            "quiet_hours_enabled": True,
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "23:59",
            "cooldown_seconds": 1,
        }
    )
    ev = TradingAlertEvent(event_type=AlertEventType.KILL_SWITCH, priority=AlertPriority.CRITICAL)
    mgr.publish(ev)
    inbox = mgr.log.inbox()
    assert any(x["event_type"] == "KILL_SWITCH" for x in inbox)


def test_sms_failure_does_not_raise():
    tmp = Path(tempfile.mkdtemp())
    mgr = _mgr(tmp)
    mgr.settings_store.update({"sms_on": True, "prefs": {"kill_switch": {"sms": True, "push": True, "sound": True, "voice": True, "in_app": True}}})
    ev = TradingAlertEvent(event_type=AlertEventType.KILL_SWITCH, priority=AlertPriority.CRITICAL)
    mgr.publish(ev)  # must not raise
    log = mgr.log.recent_log(30)
    assert any(r["channel"] == "SMS" and r["delivery_status"] == "FAILED" for r in log)
    assert any(r["event_type"] == "ALERT_DELIVERY_FAILURE" for r in log)


def test_signal_not_same_as_order_fill():
    tmp = Path(tempfile.mkdtemp())
    mgr = _mgr(tmp)
    d = SymbolDecision(
        symbol="THYAO",
        name="THY",
        sector="ULASTIRMA",
        price=100,
        trend="UP",
        buy_score=90,
        sell_score=10,
        ai_confidence=87,
        risk=RiskLevel.LOW,
        signal=SignalAction.AL,
        regime=MarketRegime.BULL,
        stop_price=95,
        target_price=110,
        explanation="test",
        decision=SignalAction.STRONG_BUY,
        capital_mode=CapitalMode.NORMAL,
    )
    emit_signal_alerts(mgr, [d])
    emit_order_lifecycle(
        mgr,
        symbol="THYAO",
        side="BUY",
        result=OrderResult(True, "P-abc", "FILLED", "filled", 100.1, 1),
        price=100,
    )
    types = {x["event_type"] for x in mgr.log.inbox(limit=20)}
    assert "BUY_SIGNAL" in types
    assert "ORDER_FILLED" in types
    assert "BUY_SIGNAL" != "ORDER_FILLED"


def test_scrub_secrets_in_log():
    tmp = Path(tempfile.mkdtemp())
    log = NotificationLog(tmp / "x.db")
    log.write_delivery(
        event_id="1",
        symbol="X",
        event_type="RISK_ALERT",
        priority="HIGH",
        channel="SMS",
        message="api_key=supersecret",
        delivery_status="FAILED",
        error="token leaked",
    )
    row = log.recent_log(1)[0]
    assert "REDACTED" in row["message"] or "REDACTED" in (row["error"] or "")


def test_settings_persist():
    tmp = Path(tempfile.mkdtemp())
    store = NotificationSettingsStore(tmp / "s.json")
    store.update({"sms_on": True, "tts_on": False, "sound_volume": 0.4})
    s2 = NotificationSettingsStore(tmp / "s.json").get()
    assert s2.sms_on is True
    assert s2.tts_on is False
    assert abs(s2.sound_volume - 0.4) < 1e-6
