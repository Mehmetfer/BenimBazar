"""Phase 1 CRYPTO / Paribu foundation — isolation + safety (no HTTP)."""

from __future__ import annotations

import os

import pytest

from config.settings import settings
from crypto.db import schema_recommendation
from crypto.market import MarketType
from crypto.providers.factory import create_crypto_provider
from crypto.providers.paribu import ParibuMarketDataProvider, RequiredCryptoProvider
from crypto.safety import crypto_provenance_fields, gate_crypto_provider, is_mock_crypto_provider_name
from crypto.service import CryptoFoundationService
from crypto.symbols import CryptoSymbolMapper, normalize_crypto_app_symbol, parse_crypto_symbol, to_display_symbol
from data.providers import SimulatedProvider, create_provider
from data.validation import AppEnvironment, MarketDataGateCode
from strategy.service import TradingService


def test_default_crypto_disabled():
    assert settings.crypto_enabled is False
    assert settings.paribu_enabled is False


def test_market_type_parse():
    assert MarketType.parse("BIST") == MarketType.BIST
    assert MarketType.parse("CRYPTO") == MarketType.CRYPTO
    assert MarketType.parse("paribu") == MarketType.CRYPTO
    assert MarketType.parse(None) == MarketType.BIST


def test_symbol_normalization_does_not_assume_paribu_wire():
    assert normalize_crypto_app_symbol("BTC/USDT") == "BTC_USDT"
    assert normalize_crypto_app_symbol("eth-usdt") == "ETH_USDT"
    assert to_display_symbol("BTC_USDT") == "BTC/USDT"
    ref = parse_crypto_symbol("XRP/USDT")
    assert ref is not None
    assert ref.base == "XRP" and ref.quote == "USDT"
    mapper = CryptoSymbolMapper()
    assert mapper.to_provider("BTC_USDT") is None  # no invented mapping
    mapper.register("BTC/USDT", "BTCTRY")  # example only — not live
    assert mapper.to_provider("BTC_USDT") == "BTCTRY"
    assert mapper.to_app("BTCTRY") == "BTC_USDT"


def test_create_crypto_provider_disabled_is_required():
    p = create_crypto_provider("paribu", crypto_enabled=False)
    assert isinstance(p, RequiredCryptoProvider)
    assert p.has_market_data() is False
    assert p.list_symbols() == []


def test_paribu_live_provider_when_enabled(monkeypatch):
    object.__setattr__(settings, "paribu_enabled", True)
    try:
        p = create_crypto_provider(
            "paribu", crypto_enabled=True, app_env="DEVELOPMENT", enable_websocket=False
        )
        assert isinstance(p, ParibuMarketDataProvider)
        assert p.is_stub is False
        assert p.is_real_provider is True
        assert p.api_base.startswith("https://")
        prov = p.provenance()
        assert prov["market_type"] == "CRYPTO"
        assert prov["provider"] == "paribu"
    finally:
        object.__setattr__(settings, "paribu_enabled", False)


def test_production_rejects_mock_crypto_name():
    assert is_mock_crypto_provider_name("simulated")
    p = create_crypto_provider("mock", crypto_enabled=True, app_env="PRODUCTION")
    assert isinstance(p, RequiredCryptoProvider)
    assert "PRODUCTION" in p.reason or "mock" in p.reason.lower()


def test_gate_live_signals_still_blocked():
    """Default CRYPTO_SIGNALS_ENABLED=false → live MD OK but signals_allowed false."""
    from tests.test_paribu_live import ORDERBOOK_SAMPLE, TICKER_SAMPLE, _client_with

    object.__setattr__(settings, "paribu_enabled", True)
    object.__setattr__(settings, "crypto_signals_enabled", False)
    try:
        http = _client_with({"/market/ticker": TICKER_SAMPLE, "/orderbook": ORDERBOOK_SAMPLE})
        p = ParibuMarketDataProvider(http=http, enable_websocket=False)
        gate = gate_crypto_provider(p, app_env=AppEnvironment.DEVELOPMENT, crypto_enabled=True)
        assert gate.ok is True
        assert gate.signals_allowed is False
        assert gate.code == MarketDataGateCode.OK
    finally:
        object.__setattr__(settings, "paribu_enabled", False)
        object.__setattr__(settings, "crypto_signals_enabled", False)


def test_crypto_service_scan_empty():
    svc = CryptoFoundationService()
    assert svc.scan() == []
    st = svc.status()
    assert st["market_type"] == "CRYPTO"
    assert st["signals_allowed"] is False
    assert st["tradeable"] is False
    assert st["live_trading"] is False
    cat = svc.markets_catalog()
    assert cat["active_default"] == "BIST"
    assert any(m["id"] == "CRYPTO" for m in cat["markets"])


def test_provenance_stamp():
    d = crypto_provenance_fields(provider_id="paribu", data_source_kind="REQUIRED")
    assert d == {"market_type": "CRYPTO", "data_source_kind": "REQUIRED", "provider": "paribu"}


def test_db_recommendation_no_migration():
    rec = schema_recommendation()
    assert rec["migrate_now"] is False
    assert rec["duplicate_database"] is False


def test_bist_provider_factory_untouched():
    p = create_provider("simulated")
    assert isinstance(p, SimulatedProvider)
    assert len(p.list_symbols()) == 10


def test_bist_trading_service_unaffected_by_crypto_package():
    """Regression: BIST scan still works; crypto module not in decision path."""
    svc = TradingService()
    assert type(svc.provider).__name__ in {"SimulatedProvider", "RequiredLiveProvider", "HttpLiveProviderStub"}
    # CryptoFoundationService is separate
    c = CryptoFoundationService()
    assert c.market_type == MarketType.CRYPTO
    decisions = svc.scan()
    # With simulated + DEVELOPMENT, expect universe-sized decisions (or empty if gated)
    assert isinstance(decisions, list)
    # Crypto scan never feeds BIST
    assert c.scan() == []


def test_crypto_api_routes_exist():
    from fastapi.testclient import TestClient
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/markets")
    assert r.status_code == 200
    body = r.json()
    assert body["active_default"] == "BIST"
    r2 = client.get("/api/crypto/status")
    assert r2.status_code == 200
    assert r2.json()["market_type"] == "CRYPTO"
    assert r2.json()["signals_allowed"] is False
    r3 = client.get("/api/crypto/scan")
    assert r3.status_code == 200
    assert r3.json()["signals"] == []
    # BIST daily still works
    r4 = client.get("/api/daily")
    assert r4.status_code == 200
    assert "daily" in r4.json()
