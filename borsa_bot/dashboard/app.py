from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import settings
from strategy.service import TradingService
from backtest.runner import run_simple_backtest
from analytics.reports import daily_market_report, top_opportunities
from walk_forward.runner import run_walk_forward
from monte_carlo.simulator import run_monte_carlo

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


@app.get("/api/opportunities")
def opportunities() -> dict:
    dash = service.dashboard()
    return top_opportunities(dash.get("universe") or [])


@app.get("/api/daily-report")
def daily_report() -> dict:
    return daily_market_report(service.dashboard())


@app.get("/api/walk-forward")
def walk_forward(symbol: str = "THYAO") -> dict:
    rep = run_walk_forward(symbol.upper())
    return {
        "symbol": rep.symbol,
        "oos_pass_rate": rep.oos_pass_rate,
        "gate_ok": rep.gate_ok,
        "note": rep.note,
        "folds": [f.__dict__ for f in rep.folds],
        "live_allowed": False,  # hard rule: never auto-enable LIVE
    }


@app.get("/api/monte-carlo")
def monte_carlo() -> dict:
    # Illustrative trade PnL sample until real trade history wired
    sample = [1200, -800, 900, -500, 1500, -700, 400, -1100, 2000, -300]
    return run_monte_carlo(sample).__dict__


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


if any(STATIC.iterdir()):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
