"""Manual BIST100 paper trade tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from config.models import MarketRegime, RiskLevel, SignalAction, SymbolDecision
from dashboard.app import app
from data.validation import MarketDataGateCode, MarketDataGateResult
from portfolio.ledger import PortfolioLedger
from strategy.service import TradingService


def test_paper_trade_api_validation():
    client = TestClient(app)
    r = client.post("/api/paper/trade", json={"symbol": "THYAO", "side": "HOLD"})
    assert r.status_code == 400


def _gate_ok():
    return MarketDataGateResult(
        ok=True,
        code=MarketDataGateCode.OK,
        signals_allowed=True,
        note="test",
        environment="DEVELOPMENT",
    )


def test_manual_paper_buy_and_sell(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        svc = TradingService()
        db = Path(tmp) / "paper.db"
        svc.ledger = PortfolioLedger(db_path=db)
        svc.broker.ledger = svc.ledger
        svc.risk.ledger = svc.ledger

        class FakeQuote:
            price = 300.0
            sector = "Havacılık"
            spread_pct = 0.1

        class FakeBar:
            def __init__(self, close=300.0):
                self.ts = None
                self.open = self.high = self.low = self.close = close
                self.volume = 1_000_000

        def fake_bars(_s, n):
            return [FakeBar(298 + (i % 7)) for i in range(max(220, n))]

        class FakeMeta:
            freshness = type("F", (), {"value": "FRESH"})()

        def fake_scan(self, symbols=None):
            return [
                SymbolDecision(
                    symbol="THYAO",
                    name="THY",
                    sector="Havacılık",
                    price=300.0,
                    trend="NEUTRAL",
                    buy_score=66.0,
                    sell_score=10.0,
                    ai_confidence=70.0,
                    risk=RiskLevel.LOW,
                    signal=SignalAction.BEKLE,
                    regime=MarketRegime.NEUTRAL,
                    stop_price=290.0,
                    target_price=310.0,
                    explanation="wait",
                    decision=SignalAction.WAIT,
                )
            ]

        monkeypatch.setattr(svc.provider, "get_quote", lambda _s: FakeQuote())
        monkeypatch.setattr(svc.provider, "get_bars", fake_bars)
        monkeypatch.setattr(svc.provider, "has_market_data", lambda: True)
        monkeypatch.setattr(svc.provider, "is_fresh", lambda _age=60: True)
        monkeypatch.setattr(svc.provider, "source_meta", lambda _sec: FakeMeta())
        monkeypatch.setattr(TradingService, "scan", fake_scan)
        monkeypatch.setattr("strategy.service.gate_market_data_for_scan", lambda *a, **k: _gate_ok())

        buy = svc.execute_manual_paper("THYAO", "BUY")
        assert buy.get("ok") is True
        assert svc.ledger.get_position("THYAO") is not None

        sell = svc.execute_manual_paper("THYAO", "SELL")
        assert sell.get("ok") is True
        assert svc.ledger.get_position("THYAO") is None


def test_manual_paper_custom_quantity(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        svc = TradingService()
        db = Path(tmp) / "paper.db"
        svc.ledger = PortfolioLedger(db_path=db)
        svc.broker.ledger = svc.ledger
        svc.risk.ledger = svc.ledger

        class FakeQuote:
            price = 100.0
            sector = "Bankacılık"
            spread_pct = 0.1

        class FakeBar:
            def __init__(self, close=100.0):
                self.ts = None
                self.open = self.high = self.low = self.close = close
                self.volume = 1_000_000

        def fake_bars(_s, n):
            return [FakeBar(98 + (i % 5)) for i in range(max(220, n))]

        monkeypatch.setattr(svc.provider, "get_quote", lambda _s: FakeQuote())
        monkeypatch.setattr(svc.provider, "get_bars", fake_bars)
        monkeypatch.setattr(svc.provider, "has_market_data", lambda: True)
        monkeypatch.setattr(svc.provider, "is_fresh", lambda _age=60: True)
        monkeypatch.setattr(
            svc.provider,
            "source_meta",
            lambda _sec: type("M", (), {"freshness": type("F", (), {"value": "FRESH"})()})(),
        )
        monkeypatch.setattr(TradingService, "scan", lambda self, symbols=None: [])
        monkeypatch.setattr("strategy.service.gate_market_data_for_scan", lambda *a, **k: _gate_ok())

        buy = svc.execute_manual_paper("GARAN", "BUY", quantity=10, price=100.0)
        assert buy.get("ok") is True
        assert svc.ledger.get_position("GARAN").quantity == 10


def test_ledger_topup():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = PortfolioLedger(db_path=Path(tmp) / "paper.db")
        start = ledger.cash
        ledger.topup(100_000)
        assert ledger.cash == start + 100_000
