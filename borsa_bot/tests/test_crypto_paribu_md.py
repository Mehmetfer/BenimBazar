"""Paribu crypto MD upgrades — bid/ask honesty, trade store, health, discovery."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from crypto.http_client import ParibuHTTPClient
from crypto.markets import build_market_catalog
from crypto.providers.factory import create_crypto_provider
from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.rest import RawTicker, fetch_recent_trades, parse_ticker_row
from crypto.trade_store import CryptoTradeStore
from crypto.rest import RawTrade
from data.integrity import MarketSession


class _FakeHTTP:
    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def open(self, req: Request, timeout: float = 15):  # noqa: ANN001
        url = req.full_url
        self.calls.append(url)
        for key, payload in self.routes.items():
            if key in url:
                if isinstance(payload, Exception):
                    raise payload
                body = json.dumps(payload).encode()
                return _Resp(200, {"Content-Type": "application/json"}, body)
        raise HTTPError(url, 404, "not found", hdrs=None, fp=BytesIO(b"{}"))


class _Resp:
    def __init__(self, status: int, headers: dict, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


TICKER = [
    {
        "market": "btc_tl",
        "low": "100",
        "high": "120",
        "first": "110",
        "last": "115",
        "volume": "12.5",
        "pair_volume": "1400",
        "change": "5",
        "percentage": "4.5",
        "average": "112",
    },
    {
        "market": "eth_usdt",
        "low": "1",
        "high": "2",
        "first": "1.5",
        "last": "1.8",
        "volume": "100",
        "pair_volume": "180",
        "change": "0.1",
        "percentage": "1",
        "average": "1.6",
    },
]
BOOK = {
    "timestamp": int(datetime.now(timezone.utc).timestamp()),
    "bids": [["114", "0.5"]],
    "asks": [["116", "0.4"]],
}
TRADES = [
    {
        "price": "115",
        "amount": "0.01",
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trade": "buy",
    }
]


def _client(routes: dict[str, Any]) -> ParibuHTTPClient:
    return ParibuHTTPClient(api_base="https://api.paribu.com", min_interval_sec=0.01, opener=_FakeHTTP(routes))


def test_crypto_provider_initialization_disabled():
    p = create_crypto_provider(crypto_enabled=False)
    assert isinstance(p, RequiredCryptoProvider)
    assert p.has_market_data() is False
    h = p.health_dict()
    assert h["connected"] is False
    assert "NO MOCK" in h["note"] or "mock" in h["note"].lower() or "off" in h["note"].lower()


def test_symbol_discovery_and_catalog(tmp_path: Path):
    http = _client({"/market/ticker": TICKER})
    p = ParibuMarketDataProvider(
        http=http, enable_websocket=False, trade_store=CryptoTradeStore(tmp_path / "t.db")
    )
    p.tick()
    syms = p.list_symbols()
    assert len(syms) == 2
    assert "BTC_TL" in syms
    markets = p.list_markets()
    assert len(markets) == 2
    assert markets[0].provider_symbol.endswith("_tl") or markets[0].provider_symbol.endswith("_usdt")
    assert markets[0].precision == "UNKNOWN"


def test_symbol_normalization_matrix():
    rows = [parse_ticker_row(x) for x in TICKER]
    cat = build_market_catalog(rows)
    by = {m.canonical_symbol: m for m in cat}
    assert by["BTC_TL"].display == "BTC/TL"
    assert by["BTC_TL"].provider_symbol == "btc_tl"


def test_ticker_does_not_invent_bid_ask(tmp_path: Path):
    http = _client({"/market/ticker": TICKER})
    p = ParibuMarketDataProvider(
        http=http, enable_websocket=False, trade_store=CryptoTradeStore(tmp_path / "t.db")
    )
    p.tick()
    with p._lock:
        q = p._quotes["BTC_TL"]
    assert q.price == 115
    assert q.bid == 0.0
    assert q.ask == 0.0
    assert p.bid_ask_known("BTC_TL") is False
    assert p.quote_spread_pct(q) is None


def test_quote_from_orderbook(tmp_path: Path):
    http = _client({"/market/ticker": TICKER, "/orderbook": BOOK})
    p = ParibuMarketDataProvider(
        http=http, enable_websocket=False, trade_store=CryptoTradeStore(tmp_path / "t.db")
    )
    p.tick()
    q = p.get_quote("BTC_TL")
    assert q.bid == 114
    assert q.ask == 116
    assert p.bid_ask_known("BTC_TL") is True
    assert p.quote_spread_pct(q) is not None


def test_ohlcv_and_trade_store(tmp_path: Path):
    store = CryptoTradeStore(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    trades = [
        RawTrade(100, 1, now - timedelta(minutes=30), "buy"),
        RawTrade(110, 1, now - timedelta(minutes=20), "sell"),
        RawTrade(105, 1, now - timedelta(minutes=5), "buy"),
    ]
    store.add_trades("BTC_TL", trades, provider_symbol="btc_tl")
    http = _client({"/market/ticker": TICKER, "/trades": TRADES})
    p = ParibuMarketDataProvider(http=http, enable_websocket=False, trade_store=store)
    p.tick()
    bars = p.get_bars("BTC_TL", lookback=240)
    assert len(bars) >= 1
    assert all(b.data_source_kind == "LIVE" for b in bars)
    assert bars[-1].ts.tzinfo is not None


def test_freshness_and_crypto_session_open(tmp_path: Path):
    http = _client({"/market/ticker": TICKER})
    p = ParibuMarketDataProvider(
        http=http, enable_websocket=False, trade_store=CryptoTradeStore(tmp_path / "t.db")
    )
    p.tick()
    assert p.is_fresh(60) is True
    meta = p.source_meta()
    assert meta.market_session == MarketSession.OPEN


def test_missing_data_fail_closed(tmp_path: Path):
    err = HTTPError("https://api.paribu.com/market/ticker", 503, "down", hdrs=None, fp=BytesIO(b"{}"))
    http = _client({"/market/ticker": err})
    p = ParibuMarketDataProvider(
        http=http, enable_websocket=False, trade_store=CryptoTradeStore(tmp_path / "t.db")
    )
    p.tick()
    assert p.has_market_data() is False
    h = p.health_dict()
    assert h["connected"] is False
    assert h.get("mock_fallback") is None or h.get("mock_fallback") is False


def test_trades_limit_capped_at_20():
    """API rejects limit>20 — client must clamp."""
    calls: list[str] = []

    class CapFake(_FakeHTTP):
        def open(self, req: Request, timeout: float = 15):  # noqa: ANN001
            calls.append(req.full_url)
            if "limit=50" in req.full_url:
                raise HTTPError(req.full_url, 400, "bad", hdrs=None, fp=BytesIO(b'{"message":"limit"}'))
            return super().open(req, timeout)

    routes = {"/trades": TRADES}
    client = ParibuHTTPClient(api_base="https://api.paribu.com", min_interval_sec=0.01, opener=CapFake(routes))
    out = fetch_recent_trades(client, "btc_tl", limit=50)
    assert out  # succeeded because clamped to <=20
    assert any("limit=20" in u for u in calls)


@pytest.mark.integration
def test_live_network_paribu_health_and_discovery():
    p = ParibuMarketDataProvider(enable_websocket=False, trade_store=CryptoTradeStore(Path("/tmp/paribu_live_test.db")))
    try:
        p.tick()
        assert p.has_market_data()
        syms = p.list_symbols()
        assert len(syms) > 50
        q = p.get_quote("BTC_TL")
        assert q.price > 0 and q.bid > 0 and q.ask > 0
        assert q.data_source_kind == "LIVE"
        h = p.health_dict()
        assert h["connected"] is True
        assert h["market_count"] > 50
        assert h["ohlcv_ready"] is False or isinstance(h["ohlcv_ready"], bool)
    finally:
        p.close()
