from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .market import get_quote, list_quotes
from .portfolio import Portfolio

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="Borsa", version="0.3.0", description="Al-sat paper trading")
portfolio = Portfolio()


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    quantity: float = Field(gt=0, le=1_000_000)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mode": "paper", "ai": False}


@app.get("/api/market")
async def market() -> dict:
    quotes = list_quotes()
    return {
        "quotes": [
            {
                "symbol": q.symbol,
                "name": q.name,
                "price": q.price,
                "change_pct": q.change_pct,
            }
            for q in quotes
        ]
    }


@app.get("/api/portfolio")
async def get_portfolio() -> dict:
    return portfolio.snapshot()


@app.post("/api/buy")
async def buy(body: OrderRequest) -> dict:
    try:
        result = portfolio.buy(body.symbol, body.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"order": result, "portfolio": portfolio.snapshot()}


@app.post("/api/sell")
async def sell(body: OrderRequest) -> dict:
    try:
        result = portfolio.sell(body.symbol, body.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"order": result, "portfolio": portfolio.snapshot()}


@app.post("/api/reset")
async def reset() -> dict:
    portfolio.reset()
    return {"ok": True, "portfolio": portfolio.snapshot()}


@app.get("/api/quote/{symbol}")
async def quote(symbol: str) -> dict:
    q = get_quote(symbol)
    if q is None:
        raise HTTPException(status_code=404, detail="Hisse bulunamadı")
    return {
        "symbol": q.symbol,
        "name": q.name,
        "price": q.price,
        "change_pct": q.change_pct,
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
