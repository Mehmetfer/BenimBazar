"""Yahoo BIST + session-auto provider tests (mocked HTTP)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data.integrity import DataSourceKind, MarketSession
from data.providers import create_provider, classify_provider
from data.session_auto import SessionAutoBistProvider
from data.yahoo_bist import YahooBistMarketDataProvider


def _quote_payload(sym: str = "THYAO.IS", price: float = 300.0) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        sym: {
            "symbol": sym,
            "timestamp": [now - 900, now],
            "close": [price - 1, price],
        }
    }


def _chart_payload(n: int = 250) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    ts = [now - i * 900 for i in range(n, 0, -1)]
    closes = [100.0 + (i % 7) for i in range(n)]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": ts,
                    "indicators": {
                        "quote": [
                            {
                                "open": closes,
                                "high": [c + 1 for c in closes],
                                "low": [c - 1 for c in closes],
                                "close": closes,
                                "volume": [1000] * n,
                            }
                        ]
                    },
                }
            ]
        }
    }


def test_factory_yahoo_and_auto(monkeypatch):
    monkeypatch.setenv("APP_ENV", "DEVELOPMENT")

    def fake_get_json(url: str):
        if "/v8/finance/spark" in url:
            return _quote_payload()
        if "/v8/finance/chart/" in url:
            return _chart_payload()
        raise AssertionError(url)

    with patch.object(YahooBistMarketDataProvider, "_get_json", side_effect=fake_get_json):
        with patch("data.yahoo_bist.bist_session_now", return_value=MarketSession.OPEN):
            p = create_provider("yahoo")
            assert isinstance(p, YahooBistMarketDataProvider)
            assert classify_provider(p) == "REAL"
            assert p.has_market_data()
            q = p.get_quote("THYAO")
            assert q.price == 300.0
            assert q.data_source_kind == DataSourceKind.DELAYED.value
            bars = p.get_bars("THYAO", 240)
            assert len(bars) >= 240

            auto = create_provider("auto")
            assert isinstance(auto, SessionAutoBistProvider)
            assert auto.has_market_data()


def test_session_auto_uses_yahoo_last_when_closed(monkeypatch):
    """CLOSED must not fall back to the tiny sim universe (blank BIST100 tiles)."""
    monkeypatch.setenv("APP_ENV", "DEVELOPMENT")
    auto = SessionAutoBistProvider()

    def fake_tick(allow_closed: bool = False) -> None:
        assert allow_closed is True
        now = datetime.now(timezone.utc)
        from config.models import QuoteSnapshot
        from data.integrity import DataSourceKind

        auto._yahoo._quotes = {
            "THYAO": QuoteSnapshot(
                symbol="THYAO",
                name="THYAO",
                sector="Havacılık",
                price=300.0,
                bid=299.5,
                ask=300.5,
                volume=1.0,
                trades=1,
                ts=now,
                data_source_kind=DataSourceKind.DELAYED.value,
            ),
            "AEFES": QuoteSnapshot(
                symbol="AEFES",
                name="AEFES",
                sector="İçecek",
                price=10.0,
                bid=9.9,
                ask=10.1,
                volume=1.0,
                trades=1,
                ts=now,
                data_source_kind=DataSourceKind.DELAYED.value,
            ),
        }
        auto._yahoo._connected = True
        auto._yahoo._last_ok = now
        auto._yahoo._error = "BIST CLOSED — last/delayed Yahoo quotes"

    with patch("data.session_auto.bist_session_now", return_value=MarketSession.CLOSED):
        with patch.object(YahooBistMarketDataProvider, "tick", side_effect=fake_tick):
            auto.tick()
            assert auto._mode == "yahoo_closed"
            assert auto.kind == DataSourceKind.DELAYED
            meta = auto.source_meta()
            assert meta.market_session == MarketSession.CLOSED
            assert meta.price_label == "SON KAPANIŞ"
            assert auto.get_quote("THYAO").price == 300.0
            assert auto.get_quote("AEFES").price == 10.0


def test_session_auto_uses_sim_when_closed(monkeypatch):
    # Kept for compatibility name — behavior is yahoo-last; sim only if yahoo empty
    test_session_auto_uses_yahoo_last_when_closed(monkeypatch)
