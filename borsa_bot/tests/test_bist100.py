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

    r5 = client.get("/api/bist100/NOTREAL")
    assert r5.status_code == 404
