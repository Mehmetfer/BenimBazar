"""Full BIST catalog search (beyond XU100) — e.g. AGROT."""

from __future__ import annotations

from fastapi.testclient import TestClient

from universe.tradeable import get_instrument, load_tradeable_universe, search_tradeable


def test_agrot_in_tradeable_catalog():
    load_tradeable_universe.cache_clear()
    inst = get_instrument("AGROT")
    assert inst is not None
    assert inst.xu100 is False
    assert "Agrotech" in inst.name or "AGROTECH" in inst.name.upper()


def test_search_agrot():
    load_tradeable_universe.cache_clear()
    hits = search_tradeable("agrot")
    assert any(h.symbol == "AGROT" for h in hits)
    hits2 = search_tradeable("agrotech")
    assert any(h.symbol == "AGROT" for h in hits2)


def test_bist_search_api():
    load_tradeable_universe.cache_clear()
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/bist/search", params={"q": "AGROT"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] >= 1
    row = next(x for x in body["results"] if x["symbol"] == "AGROT")
    assert row["xu100"] is False
    assert "BIST100" in row["decision_label"]
