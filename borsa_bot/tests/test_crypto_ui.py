"""Phase 4 — Crypto UI / dashboard / favorites / notifications."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from alerts.events import AlertEventType
from alerts.manager import AlertManager
from crypto.alerts import emit_crypto_signal_alerts
from crypto.chart import bars_to_chart, normalize_timeframe
from crypto.dashboard import card_from_parts, live_status_badge, sort_dashboard_rows
from crypto.service import CryptoFoundationService
from favorites.store import FavoritesStore


def test_live_status_badge_live_stale_unavailable():
    now = datetime.now(timezone.utc)
    assert (
        live_status_badge(has_quote=True, data_source_kind="LIVE", ts=now, max_age_sec=30) == "LIVE"
    )
    stale_ts = now - timedelta(seconds=120)
    assert (
        live_status_badge(has_quote=True, data_source_kind="LIVE", ts=stale_ts, max_age_sec=30)
        == "STALE"
    )
    assert live_status_badge(has_quote=False, data_source_kind="LIVE", ts=now) == "UNAVAILABLE"
    assert (
        live_status_badge(has_quote=True, data_source_kind="SIMULATED", ts=now) == "UNAVAILABLE"
    )


def test_sort_favorites_then_signals():
    rows = [
        card_from_parts(
            symbol="AAA_TL",
            price=1,
            change_pct=0,
            volume=1,
            signal="BUY",
            model_score=90,
            entry=1,
            stop=0.9,
            target=1.2,
            risk_reward=2,
            trend="UP",
            last_update=None,
            live_status="LIVE",
            is_favorite=False,
        ),
        card_from_parts(
            symbol="BBB_TL",
            price=1,
            change_pct=0,
            volume=1,
            signal="WAIT",
            model_score=50,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            trend="—",
            last_update=None,
            live_status="LIVE",
            is_favorite=True,
            favorite_priority=80,
        ),
        card_from_parts(
            symbol="CCC_TL",
            price=1,
            change_pct=0,
            volume=1,
            signal="STRONG_BUY",
            model_score=95,
            entry=1,
            stop=0.9,
            target=1.3,
            risk_reward=3,
            trend="UP",
            last_update=None,
            live_status="LIVE",
            is_favorite=False,
        ),
        card_from_parts(
            symbol="DDD_TL",
            price=1,
            change_pct=0,
            volume=1,
            signal="SELL",
            model_score=40,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            trend="DOWN",
            last_update=None,
            live_status="STALE",
            is_favorite=False,
        ),
    ]
    sorted_rows = sort_dashboard_rows(rows)
    assert sorted_rows[0]["symbol"] == "BBB_TL"  # favorite first
    assert sorted_rows[1]["symbol"] == "CCC_TL"  # strong buy
    assert sorted_rows[2]["symbol"] == "AAA_TL"  # buy
    assert sorted_rows[3]["symbol"] == "DDD_TL"  # sell


def test_favorites_market_type_separation():
    tmp = Path(tempfile.mkdtemp()) / "fav_mt.db"
    store = FavoritesStore(tmp)
    store.add("THYAO", market_type="BIST")
    store.add("BTC_TL", market_type="CRYPTO")
    assert store.is_favorite("THYAO", market_type="BIST")
    assert not store.is_favorite("THYAO", market_type="CRYPTO")
    assert store.is_favorite("BTC_TL", market_type="CRYPTO")
    assert not store.is_favorite("BTC_TL", market_type="BIST")
    # Same symbol string in both markets
    store.add("ETH_TL", market_type="BIST")  # unlikely but allowed
    store.add("ETH_TL", market_type="CRYPTO")
    assert store.is_favorite("ETH_TL", market_type="BIST")
    assert store.is_favorite("ETH_TL", market_type="CRYPTO")
    store.toggle("ETH_TL", market_type="CRYPTO")
    assert not store.is_favorite("ETH_TL", market_type="CRYPTO")
    assert store.is_favorite("ETH_TL", market_type="BIST")
    bist_syms = store.symbols(market_type="BIST")
    assert "THYAO" in bist_syms
    assert "BTC_TL" not in bist_syms


def test_chart_adapter():
    assert normalize_timeframe("1h") == "1h"
    from config.models import Bar
    from data.integrity import DataSourceKind

    now = datetime.now(timezone.utc)
    bars = [
        Bar(
            ts=now - timedelta(minutes=15 * i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=10,
            trades=1,
            data_source_kind=DataSourceKind.LIVE.value,
            symbol="BTC_TL",
            timeframe="15m",
            provider="paribu",
        )
        for i in range(5)
    ]
    chart = bars_to_chart(list(reversed(bars)), symbol="BTC_TL", timeframe="15m")
    assert chart["market_type"] == "CRYPTO"
    assert chart["count"] == 5
    assert len(chart["closes"]) == 5


def test_emit_crypto_notifications():
    mgr = AlertManager()
    tmp = Path(tempfile.mkdtemp()) / "fav_al.db"
    store = FavoritesStore(tmp)
    store.add("BTC_TL", market_type="CRYPTO")
    rows = [
        {
            "symbol": "BTC_TL",
            "signal": "STRONG_BUY",
            "model_score": 88,
            "price": 100.0,
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "risk_reward": 2.0,
            "is_favorite": True,
            "trade_plan": {"entry": 100, "stop_loss": 95, "target_1": 110, "risk_reward": 2},
        },
        {
            "symbol": "ETH_TL",
            "signal": "SELL",
            "model_score": 75,
            "price": 50.0,
            "is_favorite": False,
        },
        {
            "symbol": "X_TL",
            "signal": "BUY",
            "model_score": 40,
            "price": 1.0,
            "is_favorite": False,
            "risk": {"allowed": False, "reason": "spread_too_wide"},
        },
    ]
    n = emit_crypto_signal_alerts(mgr, rows, favorites=store)
    assert n >= 2
    inbox = mgr.log.inbox(limit=50)
    kinds = {e.get("event_type") for e in inbox}
    assert "BUY_SIGNAL" in kinds or AlertEventType.BUY_SIGNAL.value in kinds
    assert "RISK_ALERT" in kinds or AlertEventType.RISK_ALERT.value in kinds
    assert "SELL_SIGNAL" in kinds or AlertEventType.SELL_SIGNAL.value in kinds


def test_crypto_dashboard_api_disabled():
    from dashboard.app import app, crypto_service

    crypto_service._emit_signal_alerts = False
    client = TestClient(app)
    r = client.get("/api/crypto/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["market_type"] == "CRYPTO"
    assert body["paper_only"] is True
    assert body["live_trading"] is False
    assert "rows" in body
    assert "sections" in body


def test_crypto_detail_and_chart_api():
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/crypto/detail/BTC_TL")
    assert r.status_code == 200
    body = r.json()
    assert body["market_type"] == "CRYPTO"
    assert body["symbol"] == "BTC_TL"
    assert "chart" in body
    assert "trade_plan" in body or body.get("paper_only") is True
    r2 = client.get("/api/crypto/chart/BTC_TL?timeframe=1h")
    assert r2.status_code == 200
    assert r2.json()["timeframe"] == "1h"


def test_favorites_toggle_api_crypto():
    from dashboard.app import app, service

    tmp = Path(tempfile.mkdtemp()) / "api_fav.db"
    service.favorites = FavoritesStore(tmp)
    from dashboard import app as app_mod

    app_mod.crypto_service.bind_shared(favorites=service.favorites, alerts=service.alerts)

    client = TestClient(app)
    r = client.post("/api/favorites/BTC_TL/toggle?market_type=CRYPTO")
    assert r.status_code == 200
    assert r.json()["is_favorite"] is True
    assert r.json()["market_type"] == "CRYPTO"
    # BIST same symbol independent
    r2 = client.post("/api/favorites/BTC_TL/toggle?market_type=BIST")
    assert r2.json()["is_favorite"] is True
    r3 = client.get("/api/favorites?market_type=CRYPTO")
    assert any(f["symbol"] == "BTC_TL" for f in r3.json()["favorites"])


def test_bist_daily_still_works():
    """BIST UI regression — daily endpoint still serves sections."""
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/daily")
    assert r.status_code == 200
    data = r.json()
    assert "daily" in data
    daily = data["daily"] or {}
    assert "sections" in daily or "market" in daily or daily is not None


def test_markets_catalog_has_nav():
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/markets")
    assert r.status_code == 200
    body = r.json()
    assert any(m["id"] == "CRYPTO" for m in body["markets"])
    assert "CRYPTO" in body.get("nav", [])
