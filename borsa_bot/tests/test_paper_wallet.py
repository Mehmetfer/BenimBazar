"""Tests for BIST paper wallet simulation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config.models import MarketRegime, RiskLevel, SignalAction, SymbolDecision
from portfolio.ledger import PortfolioLedger
from portfolio.wallet_view import paper_wallet_snapshot


def test_wallet_snapshot_empty_100k():
  with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "paper.db"
    ledger = PortfolioLedger(db_path=db)
    snap = paper_wallet_snapshot(ledger)
    assert snap["starting_cash"] == 100_000
    assert snap["cash"] == 100_000
    assert snap["equity"] == 100_000
    assert snap["total_pnl"] == 0
    assert snap["positions"] == []


def test_ledger_recent_trades_and_realized_pnl():
  with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "paper.db"
    ledger = PortfolioLedger(db_path=db)
    ledger.apply_buy("THYAO", "Havacılık", 10, 100.0, "o1", 95.0, 110.0)
    ledger.apply_sell("THYAO", 10, 105.0, "o2")
    assert ledger.realized_pnl() == 50.0
    trades = ledger.recent_trades(5)
    assert len(trades) == 2
    assert trades[0]["side"] == "SELL"
    assert trades[0]["pnl"] == 50.0


def test_paper_wallet_api():
  from dashboard.app import app

  client = TestClient(app)
  r = client.get("/api/paper/wallet")
  assert r.status_code == 200
  body = r.json()
  assert body["market"] == "BIST"
  assert body["starting_cash"] == 100_000
  assert "equity" in body
  assert "recent_trades" in body


def test_paper_wallet_init_api():
  from dashboard.app import app

  client = TestClient(app)
  r = client.post("/api/paper/wallet/init")
  assert r.status_code == 200
  body = r.json()
  assert body["ok"] is True
  assert body["wallet"]["cash"] == 100_000
  assert body["user_trading_mode"] == "AUTO"


def test_paper_wallet_topup_api():
  from dashboard.app import app

  client = TestClient(app)
  client.post("/api/paper/wallet/init")
  before = client.get("/api/paper/wallet").json()["cash"]
  r = client.post(
    "/api/paper/wallet/topup",
    json={"amount": 100_000},
  )
  assert r.status_code == 200
  body = r.json()
  assert body["ok"] is True
  assert body["added"] == 100_000
  assert body["cash"] == before + 100_000
  assert body["wallet"]["cash"] == before + 100_000


def test_follow_recommendations_buys_strong_buy(monkeypatch):
  from strategy.service import TradingService

  with tempfile.TemporaryDirectory() as tmp:
    svc = TradingService()
    svc.ledger = PortfolioLedger(db_path=Path(tmp) / "paper.db")
    svc.broker.ledger = svc.ledger
    svc.risk.ledger = svc.ledger

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
          signal=SignalAction.AL,
          regime=MarketRegime.NEUTRAL,
          stop_price=290.0,
          target_price=310.0,
          explanation="strong",
          decision=SignalAction.STRONG_BUY,
        )
      ]

    def fake_execute(self, symbol, approved=False):
      self.ledger.apply_buy(symbol, "Havacılık", 5, 300.0, "test", 290.0, 310.0)
      return {"ok": True, "symbol": symbol}

    monkeypatch.setattr(TradingService, "scan", fake_scan)
    monkeypatch.setattr(TradingService, "monitor_exits", lambda self: [])
    monkeypatch.setattr(TradingService, "execute_signal", fake_execute)

    out = svc.follow_recommendations(max_buys=1)
    assert out["ok"] is True
    assert out["bought"] == 1
    assert svc.ledger.get_position("THYAO") is not None
