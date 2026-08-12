"""BIST 100 catalog and filter service tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from universe.bist100 import (
    DATA_FILE,
    filter_companies,
    get_company,
    list_companies,
    list_sectors,
    load_bist100_dataset,
)


def test_bist100_json_has_exactly_100_unique_tickers():
    data = load_bist100_dataset()
    assert data["count"] == 100
    companies = list_companies()
    assert len(companies) == 100
    tickers = [c.ticker for c in companies]
    assert len(set(tickers)) == 100
    assert all(c.ticker and c.name and c.sector for c in companies)
    assert DATA_FILE.is_file()


def test_filter_by_ticker_name_sector():
    thy = get_company("thyao")
    assert thy is not None
    assert thy.ticker == "THYAO"
    assert thy.tradingview_symbol == "BIST:THYAO"
    assert "Hava" in thy.name or "HAVA" in thy.name.upper()

    by_q = filter_companies(q="garanti")
    assert any(c.ticker == "GARAN" for c in by_q)

    banks = filter_companies(sector="Bankacılık")
    assert len(banks) >= 5
    assert all(c.sector == "Bankacılık" for c in banks)
    assert "Bankacılık" in list_sectors()


def test_bist100_api_endpoints():
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/bist100")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 100
    assert body["count"] == 100
    assert len(body["companies"]) == 100
    assert body["companies"][0]["tradingview_symbol"].startswith("BIST:")

    r2 = client.get("/api/bist100", params={"q": "ASELS"})
    assert r2.status_code == 200
    assert r2.json()["count"] >= 1
    assert any(c["ticker"] == "ASELS" for c in r2.json()["companies"])

    r3 = client.get("/api/bist100", params={"sector": "Enerji"})
    assert r3.status_code == 200
    assert r3.json()["count"] >= 1

    r4 = client.get("/api/bist100/THYAO")
    assert r4.status_code == 200
    assert r4.json()["tradingview_symbol"] == "BIST:THYAO"

def test_bist100_analysis_endpoint(monkeypatch):
    from config.models import RiskLevel, SignalAction, SymbolDecision
    from dashboard.app import app

    def fake_scan(self, symbols=None):
        return [
            SymbolDecision(
                symbol="THYAO",
                name="THY",
                sector="Havacılık",
                price=300.0,
                trend="NEUTRAL",
                buy_score=72.0,
                sell_score=20.0,
                ai_confidence=65.0,
                risk=RiskLevel.LOW,
                signal=SignalAction.WATCH,
                regime=__import__("config.models", fromlist=["MarketRegime"]).MarketRegime.NEUTRAL,
                stop_price=290.0,
                target_price=310.0,
                explanation="test",
                decision=SignalAction.WATCH,
            )
        ]

    from dashboard import app as dash_app

    monkeypatch.setattr(dash_app.service, "scan", lambda symbols=None: fake_scan(None))

    client = TestClient(app)
    r = client.get("/api/bist100/analysis", params={"q": "THYAO"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    thy = next(c for c in body["companies"] if c["symbol"] == "THYAO")
    assert thy["price"] == 300.0
    assert thy["decision"] == "WATCH"
    assert "summary" in body


def test_bist100_analysis_sorts_strong_buy_before_buy(monkeypatch):
    from config.models import MarketRegime, RiskLevel, SignalAction, SymbolDecision
    from dashboard import app as dash_app
    from dashboard.app import app

    def fake_scan(self, symbols=None):
        return [
            SymbolDecision(
                symbol="GARAN",
                name="Garanti",
                sector="Bankacılık",
                price=120.0,
                trend="NEUTRAL",
                buy_score=62.0,
                sell_score=10.0,
                ai_confidence=60.0,
                risk=RiskLevel.LOW,
                signal=SignalAction.BUY,
                regime=MarketRegime.NEUTRAL,
                stop_price=115.0,
                target_price=125.0,
                explanation="buy",
                decision=SignalAction.BUY,
            ),
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
                signal=SignalAction.STRONG_BUY,
                regime=MarketRegime.NEUTRAL,
                stop_price=290.0,
                target_price=310.0,
                explanation="strong",
                decision=SignalAction.STRONG_BUY,
            ),
        ]

    monkeypatch.setattr(dash_app.service, "scan", lambda symbols=None: fake_scan(None))
    client = TestClient(app)
    r = client.get("/api/bist100/analysis")
    assert r.status_code == 200
    syms = [c["symbol"] for c in r.json()["companies"] if c["symbol"] in {"THYAO", "GARAN"}]
    assert syms.index("THYAO") < syms.index("GARAN")
