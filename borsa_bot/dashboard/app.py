from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import settings
from strategy.service import TradingService
from backtest.runner import run_simple_backtest

STATIC = Path(__file__).resolve().parent / "static"
STATIC.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Borsa Bot", version="0.2.0")
service = TradingService()


class ExecBody(BaseModel):
    symbol: str
    approved: bool = False


@app.get("/api/health")
def health() -> dict:
    return service.health()


@app.get("/api/dashboard")
def dashboard() -> dict:
    return service.dashboard()


@app.post("/api/execute")
def execute(body: ExecBody) -> dict:
    if settings.is_live:
        raise HTTPException(400, "LIVE disabled")
    return service.execute_signal(body.symbol.upper(), approved=body.approved)


@app.post("/api/reset")
def reset() -> dict:
    service.ledger.reset()
    return {"ok": True}


@app.get("/api/backtest")
def backtest(symbol: str = "THYAO") -> dict:
    m = run_simple_backtest(symbol.upper())
    return m.__dict__


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


if any(STATIC.iterdir()):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
