from companion.app.market import get_price, list_quotes
from companion.app.portfolio import Portfolio


def test_market_quotes() -> None:
    quotes = list_quotes()
    assert len(quotes) >= 5
    assert get_price("THYAO") is not None


def test_buy_sell(tmp_path) -> None:
    db = tmp_path / "t.db"
    p = Portfolio(db)
    before = p.cash()
    buy = p.buy("THYAO", 2)
    assert buy["side"] == "BUY"
    assert p.cash() < before
    assert any(x.symbol == "THYAO" for x in p.positions())
    sell = p.sell("THYAO", 1)
    assert sell["side"] == "SELL"
    snap = p.snapshot()
    assert snap["equity"] > 0
