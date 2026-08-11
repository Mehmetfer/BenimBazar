"""PRODUCTION mock market-data hard block — 10 acceptance tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config.models import Bar, QuoteSnapshot
from data.integrity import DataSourceKind, build_source_meta
from data.providers import RequiredLiveProvider, SimulatedProvider, create_provider
from data.validation import (
    AppEnvironment,
    MarketDataGateCode,
    gate_market_data_for_scan,
    gate_provider_selection,
    mock_allowed,
    normalize_app_env,
    validate_quote,
)
from strategy.service import TradingService


class _VerifiedLiveProvider:
    """Test-only verified live feed — not used in production runtime."""

    provider_id = "verified_live_feed"
    kind = DataSourceKind.LIVE
    display_name = "Verified Live Feed"

    def __init__(self, *, stale: bool = False, no_ts: bool = False) -> None:
        self._stale = stale
        self._no_ts = no_ts
        age = 120 if stale else 5
        self._ts = datetime.now(timezone.utc) - timedelta(seconds=age)
        self._price = 100.5
        self._bars = [
            Bar(
                ts=self._ts,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000_000,
                trades=1000,
            )
        ]

    def tick(self) -> None:
        if not self._stale:
            self._ts = datetime.now(timezone.utc)

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return list(self._bars[-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return QuoteSnapshot(
            symbol=symbol,
            name=symbol,
            sector="TEST",
            price=self._price,
            bid=100.0,
            ask=101.0,
            volume=1_000_000,
            trades=1000,
            ts=self._ts,
        )

    def list_symbols(self) -> list[str]:
        return ["THYAO"]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        return not self._stale

    def has_market_data(self) -> bool:
        return not self._no_ts

    def source_meta(self, max_age_sec: float = 30.0):
        if self._no_ts:
            return build_source_meta(
                provider_id=self.provider_id,
                kind=DataSourceKind.LIVE,
                display_name=self.display_name,
                connected=True,
                last_update=None,
                max_age_sec=max_age_sec,
            )
        return build_source_meta(
            provider_id=self.provider_id,
            kind=DataSourceKind.LIVE,
            display_name=self.display_name,
            connected=True,
            last_update=self._ts,
            max_age_sec=max_age_sec,
            live_ready=False,
        )


class _UnknownKindProvider(_VerifiedLiveProvider):
    provider_id = "mystery"

    def __init__(self) -> None:
        super().__init__()
        self.kind = None  # type: ignore[assignment]


def test_1_production_plus_real_data_allowed():
    env = AppEnvironment.PRODUCTION
    p = _VerifiedLiveProvider()
    gate = gate_market_data_for_scan(p, app_env=env, max_age_sec=30)
    assert gate.ok is True
    assert gate.signals_allowed is True
    assert gate.code == MarketDataGateCode.OK
    q = p.get_quote("THYAO")
    v = validate_quote(q, env=env, meta=p.source_meta(30), max_age_sec=30)
    assert v.signals_allowed is True


def test_2_production_plus_mock_data_blocked():
    g = gate_provider_selection("mock", AppEnvironment.PRODUCTION)
    assert g.ok is False
    assert g.code == MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION
    assert g.signals_allowed is False


def test_3_production_plus_simulated_data_blocked(monkeypatch):
    monkeypatch.setenv("APP_ENV", "PRODUCTION")
    # create_provider reads settings.app_env — patch frozen field via object.__setattr__ if needed
    import config.settings as sm

    monkeypatch.setattr(sm, "settings", sm.Settings(app_env="PRODUCTION", data_provider="simulated"), raising=False)
    p = create_provider("simulated")
    assert not isinstance(p, SimulatedProvider)
    assert isinstance(p, RequiredLiveProvider)
    gate = gate_market_data_for_scan(SimulatedProvider(seed=1), app_env="PRODUCTION", max_age_sec=30)
    assert gate.ok is False
    assert gate.code == MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION
    assert gate.signals_allowed is False


def test_4_production_plus_missing_timestamp_blocked():
    p = _VerifiedLiveProvider(no_ts=True)
    q2 = SimpleNamespace(price=100.0, ts=None)
    v = validate_quote(q2, env=AppEnvironment.PRODUCTION, max_age_sec=30)  # type: ignore[arg-type]
    assert v.ok is False
    assert v.code == MarketDataGateCode.INVALID_MARKET_DATA
    gate = gate_market_data_for_scan(p, app_env="PRODUCTION", max_age_sec=30)
    assert gate.signals_allowed is False


def test_5_production_plus_stale_data_blocked():
    p = _VerifiedLiveProvider(stale=True)
    gate = gate_market_data_for_scan(p, app_env="PRODUCTION", max_age_sec=30)
    assert gate.ok is False
    assert gate.code in {
        MarketDataGateCode.STALE_DATA,
        MarketDataGateCode.DATA_NOT_VERIFIED,
    }
    assert gate.signals_allowed is False
    q = p.get_quote("THYAO")
    v = validate_quote(q, env=AppEnvironment.PRODUCTION, meta=p.source_meta(30), max_age_sec=30)
    assert v.signals_allowed is False
    assert v.code == MarketDataGateCode.STALE_DATA


def test_6_development_plus_mock_data_allowed():
    assert mock_allowed(AppEnvironment.DEVELOPMENT)
    g = gate_provider_selection("simulated", AppEnvironment.DEVELOPMENT)
    assert g.ok is True
    p = SimulatedProvider(seed=2)
    gate = gate_market_data_for_scan(p, app_env="DEVELOPMENT", max_age_sec=30)
    assert gate.signals_allowed is True


def test_7_test_env_plus_mock_data_allowed():
    assert mock_allowed(AppEnvironment.TEST)
    g = gate_provider_selection("fake", AppEnvironment.TEST)
    assert g.ok is True
    p = SimulatedProvider(seed=3)
    gate = gate_market_data_for_scan(p, app_env="TEST", max_age_sec=30)
    assert gate.signals_allowed is True


def test_8_production_plus_invalid_price_blocked():
    q = SimpleNamespace(price=-5.0, ts=datetime.now(timezone.utc))
    v = validate_quote(q, env=AppEnvironment.PRODUCTION, max_age_sec=30)  # type: ignore[arg-type]
    assert v.ok is False
    assert v.code == MarketDataGateCode.INVALID_MARKET_DATA
    q2 = SimpleNamespace(price=float("nan"), ts=datetime.now(timezone.utc))
    v2 = validate_quote(q2, env=AppEnvironment.PRODUCTION, max_age_sec=30)  # type: ignore[arg-type]
    assert v2.ok is False


def test_9_production_plus_unknown_source_blocked():
    p = _UnknownKindProvider()
    gate = gate_market_data_for_scan(p, app_env="PRODUCTION", max_age_sec=30)
    assert gate.signals_allowed is False
    assert gate.code in {
        MarketDataGateCode.UNKNOWN_SOURCE,
        MarketDataGateCode.NO_MARKET_DATA,
        MarketDataGateCode.DATA_NOT_VERIFIED,
        MarketDataGateCode.PRODUCTION_MARKET_DATA_VIOLATION,
    }


def test_10_validation_failure_means_no_signal(monkeypatch):
    svc = TradingService()
    svc.provider = SimulatedProvider(seed=9)
    from strategy import service as svc_mod

    real_gate = svc_mod.gate_market_data_for_scan

    def prod_gate(provider, app_env="DEVELOPMENT", max_age_sec=30.0):
        return real_gate(provider, app_env="PRODUCTION", max_age_sec=max_age_sec)

    monkeypatch.setattr(svc_mod, "gate_market_data_for_scan", prod_gate)
    out = svc.scan()
    assert out == []
    assert svc.last_error
    assert (
        "PRODUCTION_MARKET_DATA_VIOLATION" in svc.last_error
        or "simulated" in svc.last_error.lower()
    )


def test_live_trading_still_disabled():
    from config.settings import settings

    svc = TradingService()
    assert settings.is_live is False
    ex = svc.execute_signal("THYAO", approved=True)
    assert ex.get("live_trading") is not True


def test_regression_dev_dashboard_still_works():
    from config.settings import settings

    svc = TradingService()
    if normalize_app_env(settings.app_env) != AppEnvironment.PRODUCTION:
        dash = svc.dashboard()
        assert "daily" in dash
        assert "favorites" in dash
        assert dash.get("live_trading") is False
        assert dash.get("live_ready") is False
        assert "market_data_gate" in dash


def test_companion_not_imported_by_strategy():
    from strategy import service as s

    src = open(s.__file__, encoding="utf-8").read()
    assert "companion" not in src
