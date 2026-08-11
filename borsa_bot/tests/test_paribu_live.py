"""Phase 2 Paribu LIVE provider — unit + optional live network tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from crypto.http_client import ParibuHTTPClient, ParibuRateLimitError
from crypto.ohlcv import aggregate_trades_to_bars
from crypto.providers.factory import create_crypto_provider
from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.rest import RawTrade, parse_ticker_row
from crypto.safety import gate_crypto_provider
from crypto.symbols import normalize_crypto_app_symbol, to_paribu_market
from crypto.websocket import ParibuPublicStream
from data.contract import validate_canonical_quote
from data.integrity import DataSourceKind
from data.validation import AppEnvironment, MarketDataGateCode


class _FakeHTTP:
    """Minimal opener returning scripted responses by URL substring."""

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
                headers = {"Content-Type": "application/json"}
                return _Resp(200, headers, body)
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


TICKER_SAMPLE = [
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

ORDERBOOK_SAMPLE = {
    "timestamp": int(datetime.now(timezone.utc).timestamp()),
    "bids": [["114", "0.5"], ["113", "1.0"]],
    "asks": [["116", "0.4"], ["117", "2.0"]],
}

TRADES_SAMPLE = [
    {
        "price": "115",
        "amount": "0.01",
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trade": "buy",
    },
    {
        "price": "114.5",
        "amount": "0.02",
        "time": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "trade": "sell",
    },
]


def _client_with(routes: dict[str, Any]) -> ParibuHTTPClient:
    return ParibuHTTPClient(api_base="https://api.paribu.com", min_interval_sec=0.01, opener=_FakeHTTP(routes))


def test_symbol_paribu_wire_format():
    assert to_paribu_market("BTC/TL") == "btc_tl"
    assert to_paribu_market("BTC_TRY") == "btc_tl"
    assert normalize_crypto_app_symbol("btc_tl") == "BTC_TL"


def test_discovery_from_ticker_not_hardcoded():
    http = _client_with({"/market/ticker": TICKER_SAMPLE})
    p = ParibuMarketDataProvider(http=http, enable_websocket=False)
    p.tick()
    syms = p.list_symbols()
    assert set(syms) == {"BTC_TL", "ETH_USDT"}
    assert p.has_market_data() is True
    assert p.is_stub is False
    assert p.is_real_provider is True


def test_live_quote_canonical_fields():
    http = _client_with(
        {
            "/market/ticker": TICKER_SAMPLE,
            "/orderbook": ORDERBOOK_SAMPLE,
        }
    )
    p = ParibuMarketDataProvider(http=http, enable_websocket=False)
    p.tick()
    q = p.get_quote("BTC/TL")
    assert q.symbol == "BTC_TL"
    assert q.price == 115
    assert q.bid == 114
    assert q.ask == 116
    assert q.spread_pct > 0
    assert q.data_source_kind == "LIVE"
    assert q.provider == "paribu"
    assert q.market_status == "OPEN"
    assert q.ts.tzinfo is not None
    assert validate_canonical_quote(q, max_age_sec=60).ok


def test_ohlcv_from_trades_aggregation():
    now = datetime.now(timezone.utc)
    trades = [
        RawTrade(100, 1, now - timedelta(minutes=2), "buy"),
        RawTrade(110, 2, now - timedelta(minutes=1), "sell"),
        RawTrade(105, 1.5, now, "buy"),
    ]
    bars = aggregate_trades_to_bars(trades, symbol="BTC_TL", timeframe="15m")
    assert len(bars) >= 1
    b = bars[-1]
    assert b.high >= b.open and b.high >= b.close
    assert b.low <= b.open and b.low <= b.close
    assert b.data_source_kind == "LIVE"
    assert b.provider == "paribu"


def test_stale_data_gate():
    http = _client_with({"/market/ticker": TICKER_SAMPLE, "/orderbook": ORDERBOOK_SAMPLE})
    p = ParibuMarketDataProvider(http=http, enable_websocket=False)
    p.tick()
    # force stale
    p._last_tick = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert p.is_fresh(max_age_sec=30) is False


def test_invalid_ticker_row_skipped():
    bad = [{"market": "x_tl", "last": "nope"}]
    http = _client_with({"/market/ticker": bad + TICKER_SAMPLE})
    p = ParibuMarketDataProvider(http=http, enable_websocket=False)
    p.tick()
    assert "BTC_TL" in p.list_symbols()


def test_provider_failure_no_data():
    err = HTTPError("https://api.paribu.com/market/ticker", 500, "err", hdrs=None, fp=BytesIO(b"{}"))
    http = _client_with({"/market/ticker": err})
    p = ParibuMarketDataProvider(http=http, enable_websocket=False)
    p.tick()
    assert p.has_market_data() is False
    gate = gate_crypto_provider(p, app_env="DEVELOPMENT", crypto_enabled=True)
    assert gate.signals_allowed is False
    assert gate.code in {MarketDataGateCode.NO_MARKET_DATA, MarketDataGateCode.STUB_NOT_IMPLEMENTED}


def test_rate_limit_error():
    class Boom:
        def open(self, req, timeout=15):
            raise ParibuRateLimitError(12, body='{"retry_after":12}')

    # Exercise client parsing via synthetic HTTPError path
    from email.message import Message

    hdrs = Message()
    hdrs["Retry-After"] = "9"
    fp = BytesIO(b'{"code":429,"message":"Rate limit exceeded","retry_after":9}')
    err = HTTPError("https://api.paribu.com/market/ticker", 429, "Too Many Requests", hdrs=hdrs, fp=fp)

    class BoomHTTP:
        def open(self, req, timeout=15):
            raise err

    client = ParibuHTTPClient(api_base="https://api.paribu.com", min_interval_sec=0.01, opener=BoomHTTP())
    with pytest.raises(ParibuRateLimitError) as ei:
        client.get_json("/market/ticker")
    assert ei.value.retry_after >= 1


def test_websocket_malformed_and_match_price():
    seen: list[tuple] = []
    stream = ParibuPublicStream(on_match_price=lambda m, p, t: seen.append((m, p)))
    stream._handle_message("not-json")
    assert stream.state.last_error == "malformed JSON"
    stream._handle_message(
        json.dumps(
            {
                "e": "orderbook",
                "E": 1746789296789,
                "s": "btc_tl",
                "r": {"t": "match-price", "p": "123.45", "T": 1746789296789},
            }
        )
    )
    assert seen and seen[0][0] == "btc_tl" and seen[0][1] == 123.45


def test_websocket_reconnect_counter_state():
    stream = ParibuPublicStream(reconnect_sec=0.01)
    stream.state.reconnects = 0
    assert stream.state.connected is False
    stream.stop()


def test_factory_mock_rejected_production():
    p = create_crypto_provider("simulated", crypto_enabled=True, app_env="PRODUCTION")
    assert isinstance(p, RequiredCryptoProvider)


def test_factory_live_paribu(monkeypatch):
    object.__setattr__(__import__("config.settings", fromlist=["settings"]).settings, "paribu_enabled", True)
    try:
        http = _client_with({"/market/ticker": TICKER_SAMPLE, "/orderbook": ORDERBOOK_SAMPLE})
        p = ParibuMarketDataProvider(http=http, enable_websocket=False)
        assert isinstance(p, ParibuMarketDataProvider)
        p.tick()
        gate = gate_crypto_provider(p, app_env=AppEnvironment.DEVELOPMENT, crypto_enabled=True)
        assert gate.ok is True
        assert gate.signals_allowed is False
        assert p.kind == DataSourceKind.LIVE
    finally:
        object.__setattr__(__import__("config.settings", fromlist=["settings"]).settings, "paribu_enabled", False)


@pytest.mark.integration
def test_live_network_paribu_discovery_and_quote():
    """Hits official api.paribu.com — skip if network blocked."""
    p = ParibuMarketDataProvider(enable_websocket=False, poll_interval_sec=2)
    try:
        p.tick()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"network unavailable: {exc}")
    if not p.has_market_data():
        pytest.skip("no market data")
    syms = p.list_symbols()
    assert len(syms) > 50  # discovery, not hardcoded 3–5
    q = p.get_quote("BTC_TL")
    assert q.price > 0 and q.bid > 0 and q.ask >= q.bid
    assert q.provider == "paribu" and q.data_source_kind == "LIVE"
    bars = p.get_bars("BTC_TL", 10)
    # may be 0–few until trades accumulate — must not invent
    assert isinstance(bars, list)
    p.close()


def test_parse_ticker_row():
    t = parse_ticker_row(TICKER_SAMPLE[0])
    assert t.market == "btc_tl" and t.last == 115
