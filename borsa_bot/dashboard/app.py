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
from crypto.service import CryptoFoundationService

STATIC = Path(__file__).resolve().parent / "static"
STATIC.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Borsa Bot", version="0.3.0")
service = TradingService()
crypto_service = CryptoFoundationService()


class ExecBody(BaseModel):
    symbol: str
    approved: bool = False


class NotificationSettingsBody(BaseModel):
    sms_on: bool | None = None
    push_on: bool | None = None
    sound_on: bool | None = None
    tts_on: bool | None = None
    sound_volume: float | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    cooldown_seconds: int | None = None
    prefs: dict | None = None


@app.get("/api/health")
def health() -> dict:
    return service.health()


@app.get("/api/markets")
def markets() -> dict:
    """Market plane catalog — BIST default; CRYPTO foundation only."""
    return crypto_service.markets_catalog()


@app.get("/api/crypto/status")
def crypto_status() -> dict:
    """CRYPTO plane status. Never mixes into BIST TradingService."""
    return crypto_service.status()


@app.get("/api/crypto/scan")
def crypto_scan() -> dict:
    """Phase 2: always empty signals (crypto strategy is Phase 3)."""
    return {
        "market_type": "CRYPTO",
        "signals": crypto_service.scan(),
        "count": 0,
        "note": "CRYPTO strategy not enabled — Phase 3",
    }


@app.get("/api/crypto/symbols")
def crypto_symbols() -> dict:
    st = crypto_service.status()
    return {
        "market_type": "CRYPTO",
        "count": st.get("symbol_count", 0),
        "symbols": st.get("symbols") or [],
        "provider": st.get("provider_id"),
        "has_market_data": st.get("has_market_data"),
    }


@app.get("/api/crypto/quote/{symbol}")
def crypto_quote(symbol: str) -> dict:
    from crypto.providers.paribu import ParibuMarketDataProvider
    from crypto.symbols import normalize_crypto_app_symbol

    if not isinstance(crypto_service.provider, ParibuMarketDataProvider):
        raise HTTPException(503, "Paribu live provider not active")
    try:
        q = crypto_service.provider.get_quote(normalize_crypto_app_symbol(symbol))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, str(exc)) from exc
    return {
        "symbol": q.symbol,
        "price": q.price,
        "bid": q.bid,
        "ask": q.ask,
        "spread_pct": q.spread_pct,
        "volume": q.volume,
        "timestamp_utc": q.ts.isoformat() if q.ts else None,
        "market_type": "CRYPTO",
        "data_source_kind": q.data_source_kind,
        "provider": q.provider,
        "market_status": q.market_status,
    }


@app.get("/api/crypto/backfill/{symbol}")
def crypto_backfill(symbol: str, timeframe: str = "15m") -> dict:
    return crypto_service.backfill(symbol, timeframe=timeframe)


@app.get("/api/dashboard")
def dashboard() -> dict:
    # Monitor exits first so STOP/TP alerts reflect real fills
    try:
        service.monitor_exits()
    except Exception:  # noqa: BLE001
        pass
    return service.dashboard()


@app.get("/api/daily")
def daily_home() -> dict:
    """Simple live trading home — integrity-first, daily opportunities."""
    try:
        service.monitor_exits()
    except Exception:  # noqa: BLE001
        pass
    dash = service.dashboard()
    # Strip any accidental client-shaped fields; source is backend-owned
    src = dash.get("data_source") or {}
    return {
        "daily": dash.get("daily"),
        "health": dash.get("health"),
        "data_source": src,
        "data_source_kind": src.get("data_source_kind") or src.get("kind"),
        "tradeable": bool(src.get("tradeable")),
        "live_ready": False,
        "live_data_provider": (dash.get("health") or {}).get("live_data_provider"),
        "principle": dash.get("principle"),
    }


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
    payload = m.to_dict() if hasattr(m, "to_dict") else dict(m.__dict__)
    payload["data_source_kind"] = "BACKTEST"
    payload["excluded_from_live_win_rate"] = True
    payload["performance_category"] = "BACKTEST"
    payload["note"] = "BACKTEST ≠ LIVE WIN RATE / LIVE performance"
    return payload


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
        "data_source_kind": "BACKTEST",
        "excluded_from_live_win_rate": True,
    }


@app.get("/api/monte-carlo")
def monte_carlo() -> dict:
    sample = [1200, -800, 900, -500, 1500, -700, 400, -1100, 2000, -300]
    return run_monte_carlo(sample).__dict__


@app.get("/api/multi-horizon")
def multi_horizon() -> dict:
    return service.multi_horizon()


@app.get("/api/ai-daily-report")
def ai_daily_report() -> dict:
    mh = service.multi_horizon()
    dash = service.dashboard()
    base = daily_market_report(dash)
    return {
        **base,
        "mode": mh.get("mode"),
        "sleeves": mh.get("sleeves"),
        "top_long_term": mh.get("top", {}).get("LONG_TERM", [])[:10],
        "top_swing": mh.get("top", {}).get("SWING", [])[:10],
        "top_day_trading": mh.get("top", {}).get("DAY_TRADING", [])[:10],
        "day_risk": mh.get("day_risk"),
        "portfolio_risk": mh.get("portfolio_risk"),
        "calibration": mh.get("calibration"),
        "cash_recommendation": mh.get("sleeves", {}).get("effective_cash_target"),
        "sections": [
            "1. BIST market regime",
            "2. Sector ranking",
            "3. Top long-term",
            "4. Top swing",
            "5. Top day trading",
            "6. Risky stocks",
            "7. KAP/news (stub if unavailable)",
            "8. Portfolio risk VaR/stress",
            "9. Cash recommendation",
            "10. No-trade conditions",
        ],
        "disclaimer": "Illustrative paper report. Not investment advice. No profit guarantee. LIVE OFF.",
    }


# --- Notification APIs (informational only; never mutate trading decisions) ---


@app.get("/api/notifications")
def notifications(limit: int = 50, unread_only: bool = False) -> dict:
    return {
        "inbox": service.alerts.log.inbox(limit=limit, unread_only=unread_only),
        "log": service.alerts.log.recent_log(limit=limit),
        "settings": service.alerts.settings_store.get().to_dict(),
        "note": "SIGNAL ≠ EXECUTION. Alerts do not place orders.",
    }


@app.post("/api/notifications/read")
def notifications_read(event_id: str | None = None) -> dict:
    n = service.alerts.log.mark_read(event_id)
    return {"ok": True, "marked": n}


@app.get("/api/notifications/settings")
def get_notification_settings() -> dict:
    return service.alerts.settings_store.get().to_dict()


@app.put("/api/notifications/settings")
def put_notification_settings(body: NotificationSettingsBody) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return service.alerts.settings_store.update(patch).to_dict()


@app.post("/api/notifications/daily-summary")
def post_daily_summary() -> dict:
    return service.daily_summary_alert()


@app.post("/api/notifications/test")
def test_notification(kind: str = "BUY_SIGNAL", symbol: str = "THYAO") -> dict:
    """Dev helper — emits a synthetic alert without placing orders."""
    from alerts.events import AlertEventType, TradingAlertEvent

    try:
        et = AlertEventType(kind.upper())
    except ValueError as exc:
        raise HTTPException(400, f"unknown kind: {kind}") from exc
    ev = TradingAlertEvent(
        event_type=et,
        symbol=symbol.upper(),
        price=100.0,
        confidence=87,
        risk_reward=2.8,
        stop=95.0,
        target=110.0,
        strategy="Test Swing",
    )
    ev.dedupe_key = f"TEST:{et.value}:{symbol}:{ev.event_id}"
    service.alerts.publish(ev)
    return {"ok": True, "event_id": ev.event_id, "type": et.value}


@app.get("/api/symbol/{symbol}")
def symbol_detail(symbol: str) -> dict:
    """Detail screen — chart placeholders, plan, forecast, integrity."""
    symbol = symbol.upper()
    decisions = {d.symbol: d for d in service.scan()}
    d = decisions.get(symbol)
    meta = service.provider.source_meta(settings.data_freshness_sec)
    if not d:
        return {
            "ok": False,
            "symbol": symbol,
            "message": "VERİ YOK" if not service.provider.has_market_data() else "symbol not found",
            "data_source": meta.to_dict(),
            "live_ready": False,
        }
    ser = service._serialize(d)
    return {
        "ok": True,
        "symbol": symbol,
        "detail": ser,
        "ai_trade_plan": ser.get("ai_trade_plan"),
        "ai_forecast": ser.get("ai_forecast"),
        "ai_reliability": ser.get("ai_reliability"),
        "prediction_history": service.predictions.history(symbol, limit=20),
        "prediction_timeline": service.predictions.timeline(symbol, limit=20),
        "news": {"available": False, "source": "UNAVAILABLE", "items": [], "note": "Gerçek haber kaynağı yok"},
        "kap": {"available": False, "source": "UNAVAILABLE", "items": [], "note": "KAP bağlantısı yok"},
        "data_source": meta.to_dict(),
        "live_ready": False,
        "note": "Detay ekranı. Ana sayfada yalnızca karar alanları gösterilir.",
    }


@app.get("/api/trade-plan/{symbol}")
def trade_plan(symbol: str) -> dict:
    """Full AI trade plan for one symbol. Plan ≠ order. LIVE default OFF."""
    decisions = {d.symbol: d for d in service.scan()}
    d = decisions.get(symbol.upper())
    if not d:
        raise HTTPException(404, "symbol not found")
    ser = service._serialize(d)
    return {
        "symbol": symbol.upper(),
        "decision": ser.get("decision"),
        "final_decision": ser.get("final_decision"),
        "signal": ser.get("signal"),
        "ai_trade_plan": ser.get("ai_trade_plan"),
        "trade_plan_legacy": ser.get("trade_plan"),
        "note": "Trade plan is not an order. Requires Risk Engine + approval. No profit guarantee.",
        "live": False,
    }
    """Full AI trade plan for one symbol. Plan ≠ order. LIVE default OFF."""
    decisions = {d.symbol: d for d in service.scan()}
    d = decisions.get(symbol.upper())
    if not d:
        raise HTTPException(404, "symbol not found")
    ser = service._serialize(d)
    return {
        "symbol": symbol.upper(),
        "decision": ser.get("decision"),
        "final_decision": ser.get("final_decision"),
        "signal": ser.get("signal"),
        "ai_trade_plan": ser.get("ai_trade_plan"),
        "trade_plan_legacy": ser.get("trade_plan"),
        "note": "Trade plan is not an order. Requires Risk Engine + approval. No profit guarantee.",
        "live": False,
    }


# --- Favorites / Watchlist (FAVORITE ≠ BUY · FAVORITE = PRIORITY ANALYSIS) ---


class FavoriteUpdateBody(BaseModel):
    notes: str | None = None
    priority: int | None = None
    strategy_preference: list[str] | None = None
    groups: list[str] | None = None
    notification_preferences: dict | None = None


class PriceAlertBody(BaseModel):
    symbol: str
    kind: str  # ABOVE|BELOW|ENTRY_ZONE|STOP|TARGET
    threshold: float | None = None


@app.get("/api/favorites")
def favorites(sort: str = "PRIORITY", group: str | None = None) -> dict:
    return service.favorites_view(sort=sort, group=group)


@app.get("/api/favorites/scanner")
def favorites_scanner() -> dict:
    view = service.favorites_view()
    return {
        "question": "Favorilerimde bugün işlem fırsatı var mı?",
        "scanner": view.get("scanner"),
        "count": len(view.get("favorites") or []),
        "principle": "FAVORITE ≠ BUY",
    }


@app.get("/api/favorites/groups")
def favorites_groups() -> dict:
    return {"groups": service.favorites.list_groups()}


@app.get("/api/favorites/performance")
def favorites_performance() -> dict:
    return service.favorites.performance()


@app.post("/api/favorites/price-alert")
def favorites_price_alert(body: PriceAlertBody) -> dict:
    if not service.favorites.is_favorite(body.symbol.upper()):
        service.favorites.add(body.symbol.upper())
    rule = service.favorites.add_price_alert(body.symbol.upper(), body.kind, body.threshold)
    return {"ok": True, "alert": rule.__dict__}


@app.post("/api/favorites/{symbol}/toggle")
def favorites_toggle(symbol: str) -> dict:
    fav = service.favorites.toggle(symbol.upper())
    return {
        "ok": True,
        "symbol": fav.symbol,
        "is_favorite": fav.active,
        "record": fav.to_dict(),
        "principle": "FAVORITE ≠ BUY · FAVORITE = PRIORITY ANALYSIS",
    }


@app.put("/api/favorites/{symbol}")
def favorites_update(symbol: str, body: FavoriteUpdateBody) -> dict:
    try:
        fav = service.favorites.update(
            symbol.upper(),
            notes=body.notes,
            priority=body.priority,
            strategy_preference=body.strategy_preference,
            notification_preferences=body.notification_preferences,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.groups is not None:
        service.favorites.set_groups(symbol.upper(), body.groups)
        fav = service.favorites.get(symbol.upper())
    return {"ok": True, "record": fav.to_dict() if fav else None}


@app.get("/api/favorites/{symbol}")
def favorites_detail(symbol: str) -> dict:
    return service.favorite_detail(symbol.upper())


# --- Prediction Tracking (§104) — MEASURES only; TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK ---


@app.get("/api/predictions/report")
def predictions_report(
    symbol: str | None = None,
    strategy: str | None = None,
    horizon: str | None = None,
    model_version: str | None = None,
    regime: str | None = None,
    sector: str | None = None,
    accuracy_bucket: str | None = None,
) -> dict:
    from prediction.rating import calibration_buckets

    # Client cannot force LIVE accuracy via query pretending source — bucket filter is server-side
    rows = service.predictions.store.list_evaluations(
        symbol=symbol.upper() if symbol else None,
        strategy=strategy,
        horizon=horizon,
        model_version=model_version,
        regime=regime,
        sector=sector,
    )
    rep = service.predictions.reliability_report(
        symbol=symbol.upper() if symbol else None,
        strategy=strategy,
        horizon=horizon,
        model_version=model_version,
        regime=regime,
        sector=sector,
        accuracy_bucket=accuracy_bucket,
    )
    by_source = service.predictions.accuracy_by_source(
        symbol=symbol.upper() if symbol else None
    )
    return {
        **rep.to_dict(),
        "calibration_buckets": calibration_buckets(rows),
        "accuracy_by_source": by_source,
        "live_accuracy": by_source.get("LIVE"),
        "principle": (
            "TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK. "
            "SIMULATED accuracy ≠ LIVE accuracy. "
            "LIVE ACCURACY shows INSUFFICIENT DATA when no LIVE history exists (not 0%). "
            "Prediction tracking does not decide trades."
        ),
    }


@app.get("/api/predictions/leaderboard")
def predictions_leaderboard(group: str = "strategy") -> dict:
    board = service.predictions.leaderboard(group_key=group)
    champ = service.predictions.champion(group_key="model_version")
    return {
        "leaderboard": board,
        "champion": champ,
        "note": "Champion requires VALIDATED+ out-of-sample style sample; no degradation.",
    }


@app.get("/api/predictions/{symbol}")
def predictions_symbol(symbol: str) -> dict:
    card = service.predictions.symbol_card(symbol.upper())
    return {
        **card,
        "history": service.predictions.history(symbol.upper(), limit=40),
        "timeline": service.predictions.timeline(symbol.upper(), limit=40),
    }


@app.post("/api/predictions/evaluate")
def predictions_evaluate() -> dict:
    """Force evaluation of due horizons using current provider prices."""

    def _px(sym: str) -> float | None:
        try:
            return float(service.provider.get_quote(sym).price)
        except Exception:  # noqa: BLE001
            return None

    n = service.predictions.evaluate_due(_px)
    return {"ok": True, "evaluated": n}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


if any(STATIC.iterdir()):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
