from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from config.settings import settings
from dashboard.daily import build_daily_home, confirmation_score, opportunity_score, signal_expired, sort_key
from data.integrity import DataSourceKind, FreshnessStatus, MarketSession, build_source_meta, bist_session_now
from data.providers import RequiredLiveProvider, SimulatedProvider, create_provider
from strategy.service import TradingService


def test_simulated_never_marked_live():
    p = SimulatedProvider(seed=1)
    meta = p.source_meta(30)
    assert meta.kind == DataSourceKind.SIMULATED
    assert meta.is_live_market is False
    assert meta.live_ready is False
    assert "SİMÜLE" in meta.price_label or "SIMUL" in meta.price_label.upper()
    assert "CANLI" not in meta.price_label or meta.price_label == "SİMÜLE FİYAT"


def test_required_provider_no_fabricated_prices():
    p = RequiredLiveProvider("test")
    assert p.has_market_data() is False
    assert p.is_fresh() is False
    meta = p.source_meta(30)
    assert meta.kind == DataSourceKind.REQUIRED
    assert meta.price_label == "VERİ YOK"
    assert meta.is_live_market is False
    try:
        p.get_quote("THYAO")
        assert False, "should raise"
    except RuntimeError as e:
        assert "NO_MARKET_DATA" in str(e)


def test_create_provider_live_without_creds_is_required():
    os.environ.pop("MARKET_DATA_URL", None)
    os.environ.pop("MARKET_DATA_TOKEN", None)
    p = create_provider("live")
    assert isinstance(p, RequiredLiveProvider)
    assert p.has_market_data() is False


def test_stale_meta():
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    meta = build_source_meta(
        provider_id="x",
        kind=DataSourceKind.LIVE,
        display_name="X",
        connected=True,
        last_update=old,
        max_age_sec=30,
    )
    assert meta.freshness == FreshnessStatus.STALE
    assert meta.is_live_market is False


def test_health_exposes_source_and_not_live_ready():
    svc = TradingService()
    h = svc.health()
    assert "data_source" in h
    assert h["live_ready"] is False
    assert h["data_source"]["kind"] in {"SIMULATED", "REQUIRED", "LIVE", "UNAVAILABLE"}
    assert "system_health" in h


def test_daily_home_ranking_and_labels():
    meta = build_source_meta(
        provider_id="simulated",
        kind=DataSourceKind.SIMULATED,
        display_name="sim",
        connected=True,
        last_update=datetime.now(timezone.utc),
        max_age_sec=30,
    )
    universe = [
        {
            "symbol": "AAA",
            "decision": "WAIT",
            "final_decision": "WAIT",
            "is_favorite": True,
            "ai_confidence": 90,
            "opportunity": {"expected_value": 0.1},
            "trade_plan": {"risk_reward": 1.2},
            "price": 10,
            "universe_ok": True,
            "indicators": {"rsi": 55, "atr": 0.2, "ema21": 10},
            "price_action": {"volume_confirmed": True, "false_breakout": False},
            "regime": "BULL",
            "trend": "UP",
            "mtf": {"5m": "BULL", "15m": "BULL", "1h": "BULL"},
            "signal_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "symbol": "BBB",
            "decision": "STRONG_BUY",
            "final_decision": "STRONG_BUY",
            "is_favorite": False,
            "ai_confidence": 88,
            "opportunity": {"expected_value": 1.0},
            "ai_trade_plan": {
                "risk_reward": 2.6,
                "entry_zone": {"low": 99, "high": 101},
                "stop_loss": 95,
                "target1": {"price": 110},
                "target2": {"price": 115},
                "target3": {"price": 120},
            },
            "price": 100,
            "universe_ok": True,
            "indicators": {"rsi": 58, "atr": 1.5, "ema21": 99},
            "price_action": {"volume_confirmed": True, "false_breakout": False},
            "regime": "BULL",
            "trend": "UP",
            "mtf": {"5m": "BULL", "15m": "BULL", "1h": "BULL", "4h": "BULL"},
            "signal_timestamp": datetime.now(timezone.utc).isoformat(),
            "ai_forecast": [
                {"horizon": "1H", "pct_base": 1.2, "arrow": "↑", "tahmin_olasiligi": 80},
                {"horizon": "3H", "pct_base": 2.0, "arrow": "↑", "tahmin_olasiligi": 76},
                {"horizon": "1D", "pct_base": 4.0, "arrow": "↑", "tahmin_olasiligi": 70},
                {"horizon": "1W", "pct_base": 8.0, "arrow": "↑", "tahmin_olasiligi": 60},
            ],
            "ai_reliability": {"gecmis_dogruluk": 74, "overall_grade": "INSUFFICIENT"},
        },
    ]
    home = build_daily_home(universe, meta, signal_ttl_sec=3600, top_n=8, signals_paused=False)
    assert home["market"]["is_live_market"] is False
    assert home["integrity"]["kind"] == "SIMULATED"
    assert home["integrity"]["live_ready"] is False
    # Strong buy should outrank favorite wait in top opportunities ordering logic
    assert sort_key(universe[1]) < sort_key(universe[0])
    tops = home["sections"]["top_opportunities"]
    assert tops
    # Main card short forecast only 1H/3H/1D
    sb = home["sections"]["strong_buy"] or home["sections"]["buy"]
    assert sb
    card = sb[0]
    assert all(f["horizon"] in {"1H", "3H", "1D"} for f in (card.get("forecast_short") or []))
    assert card.get("confidence_label")
    assert card.get("accuracy_label")
    assert "historical_accuracy" in card


def test_signal_ttl_expires():
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    assert signal_expired({"signal_timestamp": old}, ttl_sec=3600) is True
    fresh = datetime.now(timezone.utc).isoformat()
    assert signal_expired({"signal_timestamp": fresh}, ttl_sec=3600) is False


def test_confirmation_prevents_weak_strong():
    weak = {
        "trend": "DOWN",
        "indicators": {"rsi": 30, "atr": 0},
        "price_action": {"volume_confirmed": False, "false_breakout": True},
        "regime": "BEAR",
        "universe_ok": False,
        "mtf": {},
        "price": 10,
    }
    assert confirmation_score(weak) < 70


def test_required_provider_scan_empty_and_blocks_orders():
    svc = TradingService()
    svc.provider = RequiredLiveProvider("unit-test")
    assert svc.scan() == []
    dash = svc.dashboard()
    assert dash["live_ready"] is False
    assert dash["daily"]["market"]["price_label"] == "VERİ YOK"
    ex = svc.execute_signal("THYAO", approved=True)
    assert ex["ok"] is False
    assert "DATA SOURCE" in ex["message"] or "auto trading" in ex.get("message", "").lower() or ex["ok"] is False


def test_dashboard_daily_section_present():
    svc = TradingService()
    dash = svc.dashboard()
    assert "daily" in dash
    assert dash["live_ready"] is False
    assert dash["data_source"]["kind"] == "SIMULATED"
    assert dash["data_source"]["is_live_market"] is False
    m = dash["daily"]["market"]
    assert m["session_label"] in {"PİYASA AÇIK", "PİYASA KAPALI"}
    # Simulated must not claim CANLI FİYAT
    assert m["price_label"] != "CANLI FİYAT"


def test_plan_invalid_when_price_leaves_zone():
    meta = build_source_meta(
        provider_id="simulated",
        kind=DataSourceKind.SIMULATED,
        display_name="sim",
        connected=True,
        last_update=datetime.now(timezone.utc),
        max_age_sec=30,
    )
    universe = [
        {
            "symbol": "THYAO",
            "decision": "BUY",
            "final_decision": "BUY",
            "ai_confidence": 80,
            "price": 330,
            "ai_trade_plan": {
                "risk_reward": 2.0,
                "entry_zone": {"low": 323, "high": 326},
                "stop_loss": 315,
                "target1": {"price": 338},
                "target2": {"price": 352},
                "target3": {"price": 370},
            },
            "opportunity": {"expected_value": 0.5},
            "universe_ok": True,
            "indicators": {"rsi": 55, "atr": 2, "ema21": 325},
            "price_action": {"volume_confirmed": True, "false_breakout": False},
            "regime": "BULL",
            "trend": "UP",
            "mtf": {"15m": "BULL", "1h": "BULL", "4h": "BULL"},
            "signal_timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ]
    home = build_daily_home(universe, meta)
    card = home["sections"]["buy"][0]
    assert card["plan_invalid"] is True
    assert "geçersiz" in (card.get("plan_note") or "").lower()


def test_bist_session_enum():
    assert bist_session_now() in {MarketSession.OPEN, MarketSession.CLOSED}
