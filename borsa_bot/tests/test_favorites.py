from __future__ import annotations

import tempfile
from pathlib import Path

from favorites.models import FavoriteSort
from favorites.priority import compute_priority_score, display_priority_bucket, signal_strength
from favorites.store import FavoritesStore
from strategy.service import TradingService


def test_favorite_toggle_independent_of_portfolio():
    tmp = Path(tempfile.mkdtemp()) / "f.db"
    store = FavoritesStore(tmp)
    fav = store.toggle("THYAO")
    assert fav.active is True
    assert store.is_favorite("THYAO")
    store.toggle("THYAO")
    assert store.is_favorite("THYAO") is False


def test_priority_score_not_simple_average_and_no_auto_buy():
    low = compute_priority_score(
        is_favorite=True,
        decision="NO_TRADE",
        signal="ALMA",
        ai_confidence=90,
        expected_value=-0.2,
        risk_reward=1.0,
        momentum=80,
        regime="BULL",
        watchlist_priority=100,
    )
    high = compute_priority_score(
        is_favorite=False,
        decision="STRONG_BUY",
        signal="AL",
        ai_confidence=88,
        expected_value=1.2,
        risk_reward=2.6,
        momentum=70,
        regime="BULL",
        watchlist_priority=0,
    )
    # Favorite membership must not outrank a real strong edge
    assert high > low
    assert signal_strength("STRONG_BUY", "AL") > signal_strength("WATCH", "BEKLE")


def test_display_bucket_favorites_first():
    b1 = display_priority_bucket({"is_favorite": True, "decision": "STRONG_BUY", "priority_score": 80, "price_action": {}})
    b2 = display_priority_bucket({"is_favorite": False, "decision": "BUY", "priority_score": 90, "price_action": {}})
    assert b1 < b2


def test_notes_and_groups():
    tmp = Path(tempfile.mkdtemp()) / "f2.db"
    store = FavoritesStore(tmp)
    store.add("ASELS", notes="Breakout bekliyorum.")
    store.update("ASELS", strategy_preference=["LONG_TERM", "SWING"], priority=80)
    store.set_groups("ASELS", ["SWING", "YÜKSEK POTANSİYEL"])
    fav = store.get("ASELS")
    assert fav is not None
    assert "Breakout" in fav.notes
    assert "SWING" in fav.groups
    assert "LONG_TERM" in fav.strategy_preference


def test_price_alert_and_timeline():
    tmp = Path(tempfile.mkdtemp()) / "f3.db"
    store = FavoritesStore(tmp)
    store.add("GARAN")
    rule = store.add_price_alert("GARAN", "ABOVE", 200.0)
    assert rule.kind == "ABOVE"
    store.add_event("GARAN", "AI_SIGNAL", "test")
    assert store.timeline("GARAN")


def test_service_favorites_in_dashboard():
    svc = TradingService()
    # isolate favorites db via attribute swap
    tmp = Path(tempfile.mkdtemp()) / "svc.db"
    svc.favorites = FavoritesStore(tmp)
    svc.favorites.add("THYAO")
    dash = svc.dashboard()
    assert "favorites" in dash
    assert "FAVORITE" in dash["principle"] or "Favori" in dash["principle"] or "≠ BUY" in dash["principle"]
    assert any(f["symbol"] == "THYAO" for f in dash["favorites"])
    u = next(x for x in dash["universe"] if x["symbol"] == "THYAO")
    assert u["is_favorite"] is True
    assert "priority_score" in u
    view = svc.favorites_view(sort=FavoriteSort.PRIORITY.value)
    assert "scanner" in view
