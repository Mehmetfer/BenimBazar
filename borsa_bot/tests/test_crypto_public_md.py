"""Public crypto MD (OKX/Gate/Kraken) — ccxt-style sources, no Paribu required."""

from __future__ import annotations

import os

import pytest

from crypto.providers.factory import create_crypto_provider, is_live_crypto_provider
from crypto.providers.paribu import RequiredCryptoProvider
from crypto.providers.public_exchanges import (
    FailoverCryptoProvider,
    GatePublicProvider,
    OkxPublicProvider,
    build_failover_chain,
)
from crypto.symbols import normalize_crypto_app_symbol


def test_factory_auto_without_paribu(monkeypatch):
    monkeypatch.setenv("CRYPTO_ENABLED", "true")
    monkeypatch.setenv("CRYPTO_PROVIDER", "auto")
    monkeypatch.setenv("PARIBU_ENABLED", "false")
    # Reload settings is frozen — call factory with explicit flags
    p = create_crypto_provider("auto", crypto_enabled=True)
    assert is_live_crypto_provider(p) or isinstance(p, RequiredCryptoProvider)
    # In this environment OKX/Gate should work
    if is_live_crypto_provider(p):
        assert p.has_market_data()
        syms = p.list_symbols()
        assert len(syms) > 10
        # Prefer a USDT major
        target = "BTC_USDT" if "BTC_USDT" in syms else syms[0]
        q = p.get_quote(target)
        assert q.price > 0
        assert q.data_source_kind == "LIVE"
        assert q.provider
        bars = p.get_bars(target, lookback=50)
        assert len(bars) >= 10
        assert bars[0].ts <= bars[-1].ts


def test_okx_provider_live_smoke():
    p = OkxPublicProvider()
    p.tick()
    assert p.has_market_data()
    assert "BTC_USDT" in p.list_symbols() or any(s.startswith("BTC_") for s in p.list_symbols())
    sym = "BTC_USDT" if "BTC_USDT" in p.list_symbols() else next(s for s in p.list_symbols() if s.startswith("BTC_"))
    q = p.get_quote(sym)
    assert q.price > 0
    bars = p.get_bars_tf(sym, "15m", lookback=30)
    assert len(bars) >= 5


def test_gate_provider_live_smoke():
    p = GatePublicProvider()
    p.tick()
    assert p.has_market_data()
    sym = "BTC_USDT" if "BTC_USDT" in p.list_symbols() else p.list_symbols()[0]
    q = p.get_quote(sym)
    assert q.price > 0


def test_failover_picks_first_healthy():
    chain = build_failover_chain(["okx", "gate", "kraken"])
    chain.tick()
    assert chain.has_market_data()
    assert chain.active is not None
    assert chain.active.provider_id in {"okx_public", "gate_public", "kraken_public"}


def test_mock_still_rejected():
    p = create_crypto_provider("mock", crypto_enabled=True)
    assert isinstance(p, RequiredCryptoProvider)
    assert p.has_market_data() is False


def test_normalize_okx_style_symbol():
    assert normalize_crypto_app_symbol("BTC-USDT") == "BTC_USDT"
    assert normalize_crypto_app_symbol("btc/usdt") == "BTC_USDT"


def test_bist_unaffected_by_crypto_public():
    from data.providers import create_provider
    from strategy.service import TradingService

    # BIST factory untouched
    p = create_provider()
    assert p is not None
    ts = TradingService()
    assert ts.provider.has_market_data()
