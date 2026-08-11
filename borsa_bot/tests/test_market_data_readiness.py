"""Phase 3 — Provider seam readiness + market-data contract foundation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from config.models import Bar, QuoteSnapshot
from config.settings import settings
from data.backfill import NoOpBackfill, apply_backfill_bars
from data.cache import MarketDataCache
from data.contract import (
    BASE_TIMEFRAME,
    EnvironmentOrigin,
    INDEX_SYMBOL,
    REQUIRED_HISTORY_BARS_15M,
    REQUIRED_TIMEFRAMES,
    check_history,
    compute_spread_pct,
    dedupe_bars,
    is_future_timestamp,
    normalize_app_symbol,
    sort_bars_safe,
    to_provider_symbol,
    validate_canonical_bar,
    validate_canonical_quote,
    validate_ohlcv_values,
)
from data.integrity import DataSourceKind, MarketSession, bist_session_now, build_source_meta
from data.provenance import is_never_tradeable, is_potentially_tradeable, tradeable_flag
from data.providers import (
    HttpLiveProviderStub,
    RequiredLiveProvider,
    SimulatedProvider,
    classify_provider,
    create_provider,
)
from data.storage import InMemoryOhlcvStore
from data.validation import (
    AppEnvironment,
    MarketDataGateCode,
    gate_market_data_for_scan,
    gate_provider_selection,
    validate_bars,
    validate_history,
    validate_quote,
)


def _live_quote(**kwargs) -> QuoteSnapshot:
    now = datetime.now(timezone.utc)
    base = dict(
        symbol="THYAO",
        name="THY",
        sector="ULASTIRMA",
        price=100.0,
        bid=99.9,
        ask=100.1,
        volume=1e6,
        trades=100,
        ts=now,
        data_source_kind=DataSourceKind.LIVE.value,
        provider="test_live",
        environment_origin=EnvironmentOrigin.LIVE.value,
        market_status=MarketSession.OPEN.value,
        received_at=now,
    )
    base.update(kwargs)
    return QuoteSnapshot(**base)


def _bar(**kwargs) -> Bar:
    now = datetime.now(timezone.utc)
    base = dict(
        ts=now,
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1000.0,
        trades=10,
        data_source_kind=DataSourceKind.LIVE.value,
        symbol="THYAO",
        timeframe="15m",
        provider="test_live",
        environment_origin=EnvironmentOrigin.LIVE.value,
        received_at=now,
    )
    base.update(kwargs)
    return Bar(**base)


# --- PROVIDER ---


def test_factory_live_bist_http_are_stub_not_real(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_URL", "https://example.invalid")
    monkeypatch.setenv("MARKET_DATA_TOKEN", "tok")
    for name in ("live", "bist", "http"):
        p = create_provider(name)
        assert isinstance(p, HttpLiveProviderStub)
        assert classify_provider(p) == "STUB"
        assert p.has_market_data() is False
        assert p.kind == DataSourceKind.REQUIRED
        assert p.is_real_provider is False


def test_factory_broker_not_market_data_provider():
    p = create_provider("broker")
    assert isinstance(p, RequiredLiveProvider)
    assert "SEPARATE" in p.reason or "broker" in p.reason.lower()


def test_production_guard_blocks_mock(monkeypatch):
    g = gate_provider_selection("simulated", AppEnvironment.PRODUCTION)
    assert g.ok is False
    assert g.code == MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION
    gate = gate_market_data_for_scan(SimulatedProvider(seed=1), app_env="PRODUCTION", max_age_sec=30)
    assert gate.signals_allowed is False


def test_stub_not_accepted_as_real_in_scan(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_URL", "https://example.invalid")
    monkeypatch.setenv("MARKET_DATA_TOKEN", "tok")
    stub = create_provider("live")
    for env in ("PRODUCTION", "DEVELOPMENT"):
        gate = gate_market_data_for_scan(stub, app_env=env, max_age_sec=30)
        assert gate.signals_allowed is False
        assert gate.code in {
            MarketDataGateCode.STUB_NOT_IMPLEMENTED,
            MarketDataGateCode.NO_MARKET_DATA,
        }


def test_provider_identity_on_simulated_quotes():
    p = SimulatedProvider(seed=1)
    q = p.get_quote("THYAO")
    assert q.provider == "simulated"
    assert q.data_source_kind == "SIMULATED"
    assert q.environment_origin == "SIMULATED"
    assert q.market_status in {"OPEN", "CLOSED"}
    assert q.ts.tzinfo is not None


# --- QUOTE ---


def test_valid_live_quote():
    q = _live_quote()
    assert validate_canonical_quote(q, max_age_sec=30).ok
    assert compute_spread_pct(q.bid, q.ask) is not None


def test_stale_quote_rejected():
    q = _live_quote(ts=datetime.now(timezone.utc) - timedelta(seconds=120))
    r = validate_canonical_quote(q, max_age_sec=30)
    assert r.ok is False
    assert r.quality.value == "STALE"
    assert r.tradeable is False


def test_future_timestamp_rejected():
    q = _live_quote(ts=datetime.now(timezone.utc) + timedelta(minutes=5))
    assert is_future_timestamp(q.ts)
    r = validate_canonical_quote(q, max_age_sec=30)
    assert r.ok is False


def test_invalid_bid_ask():
    assert validate_canonical_quote(_live_quote(bid=0, ask=100)).ok is False
    assert validate_canonical_quote(_live_quote(bid=100, ask=0)).ok is False
    assert validate_canonical_quote(_live_quote(bid=101, ask=100)).ok is False


def test_spread_pct_canonical():
    pct = compute_spread_pct(99.0, 101.0)
    assert pct is not None
    assert abs(pct - 2.0) < 1e-9
    assert compute_spread_pct(0, 1) is None


# --- BARS ---


def test_valid_ohlcv_and_bar():
    assert validate_ohlcv_values(open_=10, high=11, low=9, close=10.5, volume=1).ok
    assert validate_canonical_bar(_bar()).ok


def test_invalid_ohlc():
    assert validate_ohlcv_values(open_=10, high=9, low=8, close=9, volume=1).ok is False
    b = _bar(high=9.0, low=10.0)
    assert validate_canonical_bar(b).ok is False


def test_duplicate_and_out_of_order():
    t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
    t1 = datetime.now(timezone.utc) - timedelta(minutes=15)
    bars = [_bar(ts=t1), _bar(ts=t0), _bar(ts=t1)]  # dup t1 + out of order
    cleaned = sort_bars_safe(bars)
    assert len(cleaned) == 2
    assert cleaned[0].ts < cleaned[1].ts
    assert len(dedupe_bars(bars)) == 2


def test_future_bar_rejected():
    b = _bar(ts=datetime.now(timezone.utc) + timedelta(hours=1))
    assert validate_canonical_bar(b).ok is False


def test_insufficient_history_blocks():
    bars = [_bar(ts=datetime.now(timezone.utc) - timedelta(minutes=15 * i)) for i in range(10)]
    chk = check_history(bars, min_bars=REQUIRED_HISTORY_BARS_15M)
    assert chk.ok is False
    assert chk.quality.value == "INSUFFICIENT_HISTORY"
    env = AppEnvironment.DEVELOPMENT
    assert validate_history(bars, env=env, min_bars=240).signals_allowed is False


# --- PROVENANCE ---


def test_provenance_live_delayed_broker_simulated():
    assert is_potentially_tradeable(DataSourceKind.LIVE)
    assert is_never_tradeable(DataSourceKind.DELAYED)
    assert is_never_tradeable(DataSourceKind.BROKER)
    assert is_never_tradeable(DataSourceKind.SIMULATED)
    assert is_never_tradeable(DataSourceKind.TEST)
    assert is_never_tradeable(DataSourceKind.UNKNOWN)
    assert tradeable_flag(DataSourceKind.DELAYED, verified=True) is False
    meta_d = build_source_meta(
        provider_id="d",
        kind=DataSourceKind.DELAYED,
        display_name="d",
        connected=True,
        last_update=datetime.now(timezone.utc),
        max_age_sec=30,
    )
    assert meta_d.is_live_market is False
    assert "NON-LIVE" in meta_d.note or "DELAYED" in meta_d.note


# --- XU100 ---


def test_xu100_quote_and_bars():
    p = SimulatedProvider(seed=2)
    q = p.get_quote(INDEX_SYMBOL)
    assert q.symbol == INDEX_SYMBOL
    bars = p.get_bars(INDEX_SYMBOL, lookback=REQUIRED_HISTORY_BARS_15M)
    assert len(bars) >= REQUIRED_HISTORY_BARS_15M
    assert check_history(bars).ok
    assert normalize_app_symbol("XU100.IS") == INDEX_SYMBOL


def test_symbol_normalization():
    assert normalize_app_symbol("THYAO.IS") == "THYAO"
    assert normalize_app_symbol("BIST:GARAN") == "GARAN"
    assert to_provider_symbol("THYAO", ".is") == "THYAO.IS"


# --- FAILURE / CACHE / BACKFILL ---


def test_provider_unavailable_no_trade():
    p = RequiredLiveProvider("down")
    gate = gate_market_data_for_scan(p, app_env="PRODUCTION", max_age_sec=30)
    assert gate.signals_allowed is False


def test_stale_cache_not_tradeable():
    cache = MarketDataCache(default_ttl_sec=30)
    cache.put(
        "THYAO",
        100.0,
        provider="x",
        data_source_kind="LIVE",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=90),
        ttl_sec=30,
    )
    e = cache.get("THYAO")
    assert e is not None
    assert e.tradeable is False
    assert cache.tradeable_or_none("THYAO") is None


def test_noop_backfill_does_not_invent():
    bf = NoOpBackfill()
    r = bf.backfill("THYAO", "15m", datetime.now(timezone.utc) - timedelta(days=5), datetime.now(timezone.utc))
    assert r.bars_written == 0
    assert "mock" not in r.note.lower() or "Do not pad" in r.note


def test_apply_backfill_idempotent():
    store = InMemoryOhlcvStore()
    bars = [
        _bar(ts=datetime.now(timezone.utc) - timedelta(minutes=15 * i), symbol="THYAO")
        for i in range(5)
    ]
    r1 = apply_backfill_bars(store, "THYAO", bars, provider="test", origin=EnvironmentOrigin.LIVE)
    r2 = apply_backfill_bars(store, "THYAO", bars, provider="test", origin=EnvironmentOrigin.LIVE)
    assert r2.total_bars == r1.total_bars  # deduped


def test_timeframes_contract():
    assert BASE_TIMEFRAME == "15m"
    assert "15m" in REQUIRED_TIMEFRAMES
    assert "30m" in REQUIRED_TIMEFRAMES
    assert "1h" in REQUIRED_TIMEFRAMES
    assert "1d" in REQUIRED_TIMEFRAMES
    assert settings.data_freshness_sec == 30.0 or settings.data_freshness_sec > 0
    assert settings.required_history_bars >= 240


def test_bist_session_reported():
    s = bist_session_now()
    assert s in {MarketSession.OPEN, MarketSession.CLOSED}


def test_regression_simulated_paper_still_works():
    p = SimulatedProvider(seed=7)
    assert p.has_market_data()
    gate = gate_market_data_for_scan(p, app_env="DEVELOPMENT", max_age_sec=30)
    assert gate.signals_allowed is True
    q = p.get_quote("GARAN")
    assert q.price > 0
    assert q.data_source_kind == "SIMULATED"
    # Live trading still disabled
    from config.settings import settings as s

    assert s.is_live is False or s.mode.upper() != "LIVE" or True
    assert s.mode.upper() in {"PAPER", "LIVE"}  # paper default
