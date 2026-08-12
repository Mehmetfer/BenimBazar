"""Daily dashboard card projection — DELAYED feed must show prices."""

from __future__ import annotations

from datetime import datetime, timezone

from dashboard.daily import simplify_card
from data.integrity import DataSourceKind, DataSourceMeta, FreshnessStatus, MarketSession


def _meta(*, kind: DataSourceKind, is_live: bool = False) -> DataSourceMeta:
    return DataSourceMeta(
        provider_id="yahoo_bist",
        kind=kind,
        display_name="Yahoo Finance BIST (public DELAYED)",
        connected=True,
        last_update=datetime.now(timezone.utc).isoformat(),
        age_seconds=5.0,
        freshness=FreshnessStatus.LIVE,
        market_session=MarketSession.OPEN,
        is_live_market=is_live,
        live_ready=False,
        note="test",
        price_label="GECİKMELİ FİYAT" if kind == DataSourceKind.DELAYED else "SİMÜLE FİYAT",
    )


def test_simplify_card_shows_delayed_yahoo_prices():
    item = {
        "symbol": "THYAO",
        "name": "THY",
        "price": 301.75,
        "change_pct": 0.1,
        "decision": "WATCH",
        "is_favorite": True,
        "ai_confidence": 50,
        "ai_forecast": [],
        "ai_reliability": {},
    }
    card = simplify_card(item, _meta(kind=DataSourceKind.DELAYED))
    assert card["price"] == 301.75
    assert card["decision"] == "WATCH"
    assert card["decision_label"] == "İZLE"
    assert card["ui_status"] == "◐ DELAYED"


def test_simplify_card_strips_when_disconnected():
    item = {"symbol": "THYAO", "price": 100.0, "decision": "BUY", "is_favorite": False}
    meta = _meta(kind=DataSourceKind.DELAYED)
    meta = DataSourceMeta(
        provider_id=meta.provider_id,
        kind=meta.kind,
        display_name=meta.display_name,
        connected=False,
        last_update=None,
        age_seconds=None,
        freshness=FreshnessStatus.DISCONNECTED,
        market_session=MarketSession.OPEN,
        is_live_market=False,
        live_ready=False,
        note="down",
        price_label="VERİ YOK",
    )
    card = simplify_card(item, meta)
    assert card["price"] is None
    assert card["decision"] == "NO_DATA"
