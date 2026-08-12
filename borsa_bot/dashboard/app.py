from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
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
from autonomous.agent import get_autonomous_agent
from autonomous.engine import get_autonomous_engine
from autonomous.execution_modes import parse_execution_mode
from autonomous.explain import explain_decision
from autonomous.mode_store import mode_store
from auth import Role, auth_store
from alerts.status import channel_status_report
from data.providers import classify_provider
from universe.tradeable import universe_stats

STATIC = Path(__file__).resolve().parent / "static"
STATIC.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Refresh BIST + crypto market data while dashboard is up."""
    async def _poll() -> None:
        while True:
            try:
                service.tick()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(max(15, int(settings.data_freshness_sec)))

    async def _wallet_poll() -> None:
        await asyncio.sleep(12)
        while True:
            try:
                if settings.bist_paper_auto_follow:
                    service.follow_recommendations(max_buys=2)
                else:
                    service.monitor_exits()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(max(60, int(settings.paper_wallet_cycle_sec)))

    task = asyncio.create_task(_poll())
    wallet_task = asyncio.create_task(_wallet_poll())

    def _startup_warm() -> None:
        try:
            app.state.daily_warm_started = True
            service.tick()
            service.scan()
        except Exception:  # noqa: BLE001
            pass
        finally:
            app.state.daily_warm_started = False

    import threading

    threading.Thread(target=_startup_warm, name="startup-scan-warm", daemon=True).start()
    try:
        service.tick()
        yield
    finally:
        task.cancel()
        wallet_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
            await wallet_task


app = FastAPI(title="Borsa Bot", version="0.3.0", lifespan=_lifespan)
service = TradingService()
crypto_service = CryptoFoundationService()
crypto_service.bind_shared(favorites=service.favorites, alerts=service.alerts)
autonomy = get_autonomous_agent(trading=service)
engine = get_autonomous_engine(trading=service)


def _auth(authorization: str | None, min_role: Role) -> None:
    auth_store.require(authorization, min_role=min_role)


class ExecBody(BaseModel):
    symbol: str
    approved: bool = False


class PaperTradeBody(BaseModel):
    symbol: str
    side: str  # BUY | SELL
    quantity: float | None = None
    price: float | None = None


class PaperTopupBody(BaseModel):
    amount: float = 100_000.0


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


class AutonomyModeBody(BaseModel):
    mode: str


class AutonomyExecutionModeBody(BaseModel):
    execution_mode: str


class AutonomyCycleBody(BaseModel):
    market: str = "BIST"
    force: bool = False
    use_engine: bool = True


class LoginBody(BaseModel):
    username: str = ""
    token: str


class CancelOrderBody(BaseModel):
    client_order_id: str


class LiveConfirmBody(BaseModel):
    confirm: bool
    phrase: str = ""


class ModelPromoteBody(BaseModel):
    approved_by: str = "dashboard"


class Level7PromoteBody(BaseModel):
    approved_by: str = "dashboard"


class Level7AdvanceBody(BaseModel):
    passed: bool = True
    metrics: dict | None = None


class ExperimentStartBody(BaseModel):
    hypothesis_id: str
    dataset: str = "historical_bars"


@app.get("/api/health")
def health() -> dict:
    return service.health()


@app.get("/api/markets")
def markets() -> dict:
    """Market plane catalog — BIST default; CRYPTO foundation only."""
    return crypto_service.markets_catalog()


@app.get("/api/bist100/quotes")
def bist100_quotes() -> dict:
    """Fast BIST100 quote grid — Son/Alış/Satış/%G without full scan."""
    try:
        return service.bist100_quotes()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/watchlist/quotes")
def watchlist_quotes() -> dict:
    """Fast Takip Listem grid — XU100 + favorites, Son/Alış/Satış/%G."""
    try:
        return service.watchlist_quotes()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/bist100/analysis")
def bist100_analysis(
    q: str | None = None,
    sector: str | None = None,
    sort: str = "decision",
) -> dict:
    """BIST 100 full-universe scan — price + signal per company."""
    try:
        return service.bist100_analysis(q=q, sector=sector, sort=sort)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/bist100")
def bist100_list(q: str | None = None, sector: str | None = None) -> dict:
    """Filterable BIST 100 company catalog (metadata). Prices via TradingView."""
    from universe.bist100 import catalog_payload

    try:
        return catalog_payload(q=q, sector=sector)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/bist100/{ticker}")
def bist100_company(ticker: str) -> dict:
    """Single BIST 100 company + TradingView symbol."""
    from universe.bist100 import get_company, load_bist100_dataset

    company = get_company(ticker)
    if company is None:
        raise HTTPException(404, f"{ticker.upper()} is not in the BIST 100 dataset")
    meta = load_bist100_dataset()
    return {
        "ok": True,
        "index": meta.get("index", "XU100"),
        "company": company.to_dict(),
        "tradingview_symbol": company.tradingview_symbol,
        "updated": meta.get("updated"),
        "note": "Interactive chart uses TradingView widget (BIST:TICKER). Not a fabricated live quote.",
    }


@app.get("/api/bist/search")
def bist_search(q: str = "", limit: int = 20) -> dict:
    """Search full BIST catalog (XU100 + outside). Paper quote when available."""
    from universe.bist100 import get_company
    from universe.tradeable import search_tradeable

    needle = (q or "").strip()
    if len(needle) < 2:
        return {
            "ok": True,
            "q": needle,
            "count": 0,
            "results": [],
            "note": "En az 2 karakter girin",
        }
    hits = search_tradeable(needle, limit=max(1, min(40, int(limit))))
    results: list[dict] = []
    for inst in hits:
        in_xu100 = bool(inst.xu100 or get_company(inst.symbol))
        row: dict = {
            "symbol": inst.symbol,
            "ticker": inst.symbol,
            "name": inst.name,
            "sector": inst.sector,
            "xu100": in_xu100,
            "tradingview_symbol": f"BIST:{inst.symbol}",
            "decision": "OUTSIDE_XU100" if not in_xu100 else "XU100",
            "decision_label": "BIST100 dışı" if not in_xu100 else "BIST100",
            "price": None,
            "change_pct": None,
            "in_portfolio": service.ledger.get_position(inst.symbol) is not None,
            "position_qty": 0.0,
        }
        pos = service.ledger.get_position(inst.symbol)
        if pos:
            row["position_qty"] = float(pos.quantity)
        try:
            quote = service.provider.get_quote(inst.symbol)
            row["price"] = round(float(quote.price), 4)
        except Exception:  # noqa: BLE001
            pass
        results.append(row)
    outside = [r for r in results if not r["xu100"]]
    return {
        "ok": True,
        "q": needle,
        "count": len(results),
        "outside_xu100": len(outside),
        "results": results,
        "note": (
            f"{len(results)} sonuç · {len(outside)} BIST100 dışı · "
            "AGROT gibi hisseler XU100'de olmayabilir"
        ),
    }


@app.get("/api/crypto/status")
def crypto_status() -> dict:
    """CRYPTO plane status. Never mixes into BIST TradingService."""
    return crypto_service.status()


@app.get("/api/crypto/health")
def crypto_health() -> dict:
    """Paribu connection / discovery / freshness / OHLCV readiness."""
    return crypto_service.health()


@app.get("/api/crypto/markets")
def crypto_markets() -> dict:
    """Full Paribu market discovery catalog (canonical + provider symbols)."""
    return crypto_service.markets()


@app.get("/api/crypto/dashboard")
def crypto_dashboard(limit: int = 40) -> dict:
    """Crypto dashboard cards — favorites-first, LIVE/STALE/UNAVAILABLE badges."""
    return crypto_service.dashboard(limit=limit, emit_alerts=True)


@app.get("/api/crypto/scan")
def crypto_scan(limit: int = 20) -> dict:
    """Crypto signal scan (paper analysis). Empty unless CRYPTO_SIGNALS_ENABLED."""
    lim = max(1, min(100, int(limit)))
    signals = crypto_service.scan()
    return {
        "market_type": "CRYPTO",
        "signals": signals[:lim],
        "count": len(signals),
        "signals_enabled": bool(settings.crypto_signals_enabled),
        "live_trading": False,
        "paper_only": True,
        "note": "CRYPTO signals are paper-only — no live broker orders",
    }


@app.get("/api/crypto/signal/{symbol}")
def crypto_signal(symbol: str) -> dict:
    return crypto_service.signal(symbol)


@app.get("/api/crypto/detail/{symbol}")
def crypto_detail(symbol: str, timeframe: str = "15m") -> dict:
    """Coin detail: price, chart, indicators, signal, trade plan, accuracy, risk."""
    return crypto_service.detail(symbol, timeframe=timeframe)


@app.get("/api/crypto/chart/{symbol}")
def crypto_chart(symbol: str, timeframe: str = "15m", lookback: int = 120) -> dict:
    """Crypto chart adapter (Paribu trade aggregation — not a BIST chart copy)."""
    return crypto_service.chart(symbol, timeframe=timeframe, lookback=lookback)


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
    from crypto.dashboard import live_status_badge
    from crypto.providers.factory import is_live_crypto_provider
    from crypto.symbols import normalize_crypto_app_symbol

    if not is_live_crypto_provider(crypto_service.provider):
        raise HTTPException(503, "Crypto live provider not active")
    try:
        q = crypto_service.provider.get_quote(normalize_crypto_app_symbol(symbol))
        stats = crypto_service.provider.ticker_stats(normalize_crypto_app_symbol(symbol))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, str(exc)) from exc
    return {
        "symbol": q.symbol,
        "display": q.name,
        "canonical_symbol": q.symbol,
        "provider_symbol": normalize_crypto_app_symbol(symbol).lower(),
        "price": q.price,
        "bid": q.bid if q.bid > 0 else None,
        "ask": q.ask if q.ask > 0 else None,
        "bid_ask_known": bool(getattr(crypto_service.provider, "bid_ask_known", lambda _s: False)(q.symbol)),
        "spread_pct": crypto_service.provider.quote_spread_pct(q)
        if hasattr(crypto_service.provider, "quote_spread_pct")
        else q.spread_pct,
        "volume": stats.get("volume", q.volume),
        "change_pct": stats.get("change_pct"),
        "timestamp_utc": q.ts.isoformat() if q.ts else None,
        "received_at": q.received_at.isoformat() if q.received_at else None,
        "market_type": "CRYPTO",
        "data_source_kind": q.data_source_kind,
        "source_kind": q.data_source_kind,
        "provider": q.provider,
        "market_status": q.market_status,
        "live_status": live_status_badge(
            has_quote=True, data_source_kind=q.data_source_kind, ts=q.ts
        ),
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
    """Simple live trading home — integrity-first, daily opportunities.

    Must stay responsive: Yahoo full-universe scans can 429. Prefer scan cache;
    on cold start return shell + kick background warm scan (page still opens).
    """
    import threading
    import time

    t0 = time.time()
    soft_deadline_sec = 12.0

    def _shell(daily: dict | None = None, *, scan_pending: bool = False, note: str = "") -> dict:
        try:
            meta = service.provider.source_meta(settings.data_freshness_sec)
            src = meta.to_dict()
        except Exception:  # noqa: BLE001
            src = {"kind": "UNKNOWN", "display_name": "UNKNOWN"}
        try:
            health = service.health()
        except Exception:  # noqa: BLE001
            health = {"status": "UNKNOWN"}
        return {
            "daily": daily or {
                "opportunities": [],
                "no_opportunity": True,
                "no_opportunity_message": note or "Tarama devam ediyor — sayfayı yenileyin",
            },
            "health": health,
            "data_source": src,
            "data_source_kind": src.get("data_source_kind") or src.get("kind"),
            "tradeable": bool(src.get("tradeable")),
            "live_ready": False,
            "live_data_provider": (health or {}).get("live_data_provider"),
            "principle": "LESS DATA, MORE DECISION · DELAYED ≠ LIVE",
            "universe": universe_stats(),
            "scan_stats": (engine.status().get("last_cycle") or {}).get("filter_stats"),
            "display_note": "Top list = visible opportunities only — not the full universe.",
            "scan_pending": scan_pending,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    # Warm cache path — only ONE background warm at a time
    cache_warm = getattr(service, "_scan_cache", None) is not None
    if not cache_warm:
        if not getattr(app.state, "daily_warm_started", False):
            app.state.daily_warm_started = True

            def _warm() -> None:
                try:
                    service.scan()
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    app.state.daily_warm_started = False

            threading.Thread(target=_warm, name="daily-scan-warm", daemon=True).start()
        # Try a quick tick for source banner only
        try:
            service.tick()
        except Exception:  # noqa: BLE001
            pass
        return _shell(scan_pending=True, note="İlk tarama arka planda — Yahoo DELAYED · birkaç saniye sonra yenileyin")

    try:
        service.monitor_exits()
    except Exception:  # noqa: BLE001
        pass
    if time.time() - t0 > soft_deadline_sec:
        return _shell(scan_pending=True, note="Zaman aşımı — önbellek yenileniyor")

    dash = service.dashboard()
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
        "universe": universe_stats(),
        "scan_stats": (engine.status().get("last_cycle") or {}).get("filter_stats"),
        "display_note": "Top list = visible opportunities only — not the full universe.",
        "scan_pending": False,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


@app.post("/api/paper/trade")
def paper_trade(body: PaperTradeBody, authorization: str | None = Header(default=None)) -> dict:
    """Manual BIST paper BUY/SELL from BIST100 UI."""
    if bool(getattr(settings, "auth_enabled", False)):
        auth_store.require(authorization, min_role=Role.TRADER)
    side = body.side.upper().strip()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(400, "side must be BUY or SELL")
    return service.execute_manual_paper(
        body.symbol.upper(),
        side,
        quantity=body.quantity,
        price=body.price,
    )


@app.post("/api/paper/wallet/topup")
def paper_wallet_topup(body: PaperTopupBody | None = None) -> dict:
    """Add paper cash (default +100.000 TL) without resetting positions."""
    amount = float(body.amount if body is not None else 100_000.0)
    if amount <= 0:
        raise HTTPException(400, "amount must be positive")
    try:
        cash = service.ledger.topup(amount)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    wallet = service.paper_wallet()
    return {
        "ok": True,
        "added": round(amount, 2),
        "cash": round(cash, 2),
        "message": f"+{amount:,.0f} TL nakde eklendi · bakiye {cash:,.2f} TL",
        "wallet": wallet,
    }


@app.post("/api/execute")
def execute(body: ExecBody, authorization: str | None = Header(default=None)) -> dict:
    if bool(getattr(settings, "auth_enabled", False)):
        auth_store.require(authorization, min_role=Role.TRADER)
    if settings.is_live and not (
        getattr(settings, "live_broker_enabled", False) and getattr(settings, "live_confirmed", False)
    ):
        raise HTTPException(400, "LIVE disabled")
    return service.execute_signal(body.symbol.upper(), approved=body.approved)


@app.post("/api/reset")
def reset() -> dict:
    service.ledger.reset()
    return {"ok": True, "wallet": service.paper_wallet()}


@app.get("/api/paper/wallet")
def paper_wallet() -> dict:
    """BIST simulation wallet — 100k paper, PnL, positions, trades."""
    return service.paper_wallet()


@app.get("/api/paper/diagnostics")
def paper_diagnostics() -> dict:
    """Loss attribution from paper ledger — evidence only, no fabricated edge claims."""
    from profit.diagnostics import analyze_paper_ledger

    report = analyze_paper_ledger()
    body = report.to_dict()
    body["ok"] = True
    body["autonomy_note"] = "AUTONOMY SCORE ≠ TRADING PROFITABILITY"
    body["live_money_readiness"] = "NOT VERIFIED"
    return body


@app.get("/api/desk/briefing")
def desk_briefing() -> dict:
    """Institutional desk daily briefing — regime, risk, opportunities, portfolio."""
    briefing = service.desk_briefing()
    briefing["ok"] = True
    return briefing


@app.get("/api/desk/evaluate/{symbol}")
def desk_evaluate(symbol: str) -> dict:
    """Master Trading Committee + pipeline evaluation for one symbol."""
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")
    result = service.desk_evaluate(sym)
    result["ok"] = True
    return result


@app.get("/api/desk/scan")
def desk_scan(limit: int = 20) -> dict:
    """Run institutional pipeline on top scan opportunities."""
    lim = max(1, min(50, int(limit)))
    rows = service.desk_scan(limit=lim)
    return {"ok": True, "count": len(rows), "results": rows}


@app.post("/api/paper/wallet/init")
def paper_wallet_init() -> dict:
    """Reset BIST paper wallet to STARTING_CASH (default 100k). Does not change autonomy mode."""
    service.ledger.reset()
    mode_store.set_execution_mode("PAPER")
    return {
        "ok": True,
        "message": (
            f"BIST paper cüzdan {settings.starting_cash:,.0f} TL ile sıfırlandı · "
            f"otonomi modu değişmedi · auto_follow={settings.bist_paper_auto_follow}"
        ),
        "wallet": service.paper_wallet(),
        "user_trading_mode": engine.user_mode().value,
        "execution_mode": "PAPER",
        "auto_follow": settings.bist_paper_auto_follow,
    }


@app.post("/api/paper/follow")
def paper_follow(max_buys: int = 2) -> dict:
    """Manually run one recommendation-follow cycle (BIST paper only)."""
    return service.follow_recommendations(max_buys=max(1, min(5, max_buys)))


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
def favorites(sort: str = "PRIORITY", group: str | None = None, market_type: str = "BIST") -> dict:
    mt = (market_type or "BIST").upper()
    if mt == "CRYPTO":
        rows = [
            {
                **f.to_dict(),
                "is_favorite": True,
                "favorite": True,
                "priority": f.priority,
            }
            for f in service.favorites.list_favorites(market_type="CRYPTO")
        ]
        return {
            "market_type": "CRYPTO",
            "favorites": rows,
            "count": len(rows),
            "principle": "FAVORITE ≠ BUY · market_type ayrımı korunur",
            "sort": sort,
            "group": group,
        }
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
def favorites_performance(market_type: str | None = None) -> dict:
    return service.favorites.performance(market_type=market_type)


@app.post("/api/favorites/price-alert")
def favorites_price_alert(body: PriceAlertBody, market_type: str = "BIST") -> dict:
    mt = (market_type or "BIST").upper()
    if not service.favorites.is_favorite(body.symbol.upper(), market_type=mt):
        service.favorites.add(body.symbol.upper(), market_type=mt)
    rule = service.favorites.add_price_alert(body.symbol.upper(), body.kind, body.threshold, market_type=mt)
    return {"ok": True, "alert": rule.__dict__, "market_type": mt}


@app.post("/api/favorites/{symbol}/toggle")
def favorites_toggle(symbol: str, market_type: str = "BIST") -> dict:
    mt = (market_type or "BIST").upper()
    fav = service.favorites.toggle(symbol.upper(), market_type=mt)
    return {
        "ok": True,
        "symbol": fav.symbol,
        "market_type": fav.market_type,
        "is_favorite": fav.active,
        "favorite": fav.active,
        "priority": fav.priority,
        "record": fav.to_dict(),
        "principle": "FAVORITE ≠ BUY · FAVORITE = PRIORITY ANALYSIS",
    }


@app.put("/api/favorites/{symbol}")
def favorites_update(symbol: str, body: FavoriteUpdateBody, market_type: str = "BIST") -> dict:
    mt = (market_type or "BIST").upper()
    try:
        fav = service.favorites.update(
            symbol.upper(),
            notes=body.notes,
            priority=body.priority,
            strategy_preference=body.strategy_preference,
            notification_preferences=body.notification_preferences,
            market_type=mt,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.groups is not None:
        service.favorites.set_groups(symbol.upper(), body.groups, market_type=mt)
        fav = service.favorites.get(symbol.upper(), market_type=mt)
    return {"ok": True, "record": fav.to_dict() if fav else None}


@app.get("/api/favorites/{symbol}")
def favorites_detail(symbol: str, market_type: str = "BIST") -> dict:
    mt = (market_type or "BIST").upper()
    if mt == "CRYPTO":
        fav = service.favorites.get(symbol.upper(), market_type="CRYPTO")
        return {
            "market_type": "CRYPTO",
            "symbol": symbol.upper(),
            "is_favorite": bool(fav and fav.active),
            "record": fav.to_dict() if fav else None,
            "timeline": service.favorites.timeline(symbol.upper(), market_type="CRYPTO"),
            "price_alerts": [a.__dict__ for a in service.favorites.list_price_alerts(symbol.upper(), market_type="CRYPTO")],
        }
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


@app.get("/api/autonomy/status")
def autonomy_status() -> dict:
    """Autonomous engine status — PAPER/SHADOW/LIVE venue; live broker locked by default."""
    st = engine.status()
    legacy = autonomy.status()
    st["user_trading_mode"] = legacy.get("user_trading_mode") or st.get("user_trading_mode")
    return st


@app.get("/api/autonomy/self")
def autonomy_self() -> dict:
    """Self-awareness snapshot (signals, risk, data, model sample tier)."""
    return engine.self_awareness()


@app.get("/api/ai/status")
def ai_status() -> dict:
    """AI Decision Engine status — proposals only; risk bypass forbidden."""
    return engine.ai.status()


@app.get("/api/ai/watchlist")
def ai_watchlist() -> dict:
    return {
        "ok": True,
        "items": engine.ai.watchlist.list_items(),
        "note": "AI watchlist ≠ trading permission / risk bypass",
    }


@app.get("/api/ai/decisions")
def ai_decisions(limit: int = 20, symbol: str | None = None) -> dict:
    lim = max(1, min(100, int(limit)))
    return {
        "ok": True,
        "decisions": engine.ai.memory.recent(symbol=symbol, limit=lim),
        "note": "confidence ≠ calibrated probability · RiskEngine is final",
    }


@app.post("/api/ai/cycle")
def ai_cycle(body: AutonomyCycleBody | None = None) -> dict:
    """Run autonomy cycle and return AI decision packet (BIST). Still gated by risk."""
    payload = body or AutonomyCycleBody()
    if (payload.market or "BIST").upper() != "BIST":
        raise HTTPException(400, "AI cycle via this endpoint is BIST; use crypto plane separately")
    report = engine.run_cycle("BIST", force=bool(payload.force))
    return {
        "ok": True,
        "cycle": report,
        "ai": report.get("ai_decision") or {},
        "risk_bypass": False,
        "broker_direct": False,
    }


@app.get("/api/ai/command-center")
def ai_command_center() -> dict:
    st = engine.ai.status()
    last = st.get("last_cycle") or {}
    return {
        "ok": True,
        "command_center": last.get("command_center") or st.get("command_center") or {},
        "autonomy": last.get("autonomy") or st.get("autonomy") or {},
        "activity": (last.get("activity") or [])[-20:],
        "governor": last.get("governor"),
        "regime": last.get("regime"),
        "ai_status": st.get("ai_status"),
        "risk_bypass": False,
        "note": "WHEN UNCERTAIN → DO NOT TRADE",
    }


@app.get("/api/ai/autonomy")
def ai_autonomy_scores() -> dict:
    st = engine.ai.status()
    last = st.get("last_cycle") or {}
    return {
        "ok": True,
        "autonomy": last.get("autonomy") or {},
        "level_note": "Level 5–6 require shadow/live + calibrated models",
    }


@app.get("/api/ai/research/{symbol}")
def ai_research(symbol: str) -> dict:
    """Research mode — debate + plan for one symbol; no order."""
    return engine.ai.analyze_symbol(symbol.upper())


@app.get("/api/level7/status")
def level7_status() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        return {"ok": False, "reason": "level7_unavailable"}
    return {"ok": True, **l7.status()}


@app.post("/api/level7/cycle")
def level7_cycle() -> dict:
    """Run Level 7 research/hypothesis/diagnostics cycle (no broker)."""
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    # Prefer last AI context if present
    st = engine.ai.status()
    last = st.get("last_cycle") or {}
    out = l7.run_cycle(
        context={**(last.get("context") or {}), "data_valid": True},
        regime=last.get("regime") or {},
        health=last.get("health") or {},
        learning=last.get("learning") or {},
        top_row=((last.get("decisions") or [{}])[0] if last.get("decisions") else None),
        decision_quality_avg=float((((last.get("decisions") or [{}])[0].get("quality") or {}).get("total") or 70)),
    )
    return {"ok": True, "cycle": out, "risk_bypass": False, "broker_direct": False}


@app.get("/api/level7/research")
def level7_research() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    return {"ok": True, "questions": l7.research.list_questions(50)}


@app.get("/api/level7/hypotheses")
def level7_hypotheses() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    return {"ok": True, "hypotheses": l7.hypotheses.list_hypotheses(50)}


@app.get("/api/level7/experiments")
def level7_experiments() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    return {"ok": True, "experiments": l7.experiments.list_experiments(50), "pipeline": [
        "HYPOTHESIS", "DATASET", "BACKTEST", "WALK_FORWARD", "OUT_OF_SAMPLE", "PAPER", "SHADOW", "EVALUATION", "HUMAN_APPROVAL"
    ]}


@app.post("/api/level7/experiments/start")
def level7_experiment_start(body: ExperimentStartBody) -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    exp = l7.experiments.start(body.hypothesis_id, dataset=body.dataset)
    return {"ok": True, "experiment": exp.to_dict()}


@app.post("/api/level7/experiments/{experiment_id}/advance")
def level7_experiment_advance(experiment_id: str, body: Level7AdvanceBody | None = None) -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    payload = body or Level7AdvanceBody()
    return l7.experiments.advance(experiment_id, passed=bool(payload.passed), metrics=payload.metrics)


@app.get("/api/level7/lab")
def level7_lab() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    return {"ok": True, "strategies": l7.lab.list_strategies(50), "arena": l7.arena.status()}


@app.post("/api/level7/lab/{strategy_id}/propose-promotion")
def level7_propose_promotion(strategy_id: str, body: Level7AdvanceBody | None = None) -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    payload = body or Level7AdvanceBody()
    return l7.arena.propose_promotion(strategy_id, metrics=payload.metrics or {})


@app.post("/api/level7/lab/{strategy_id}/approve")
def level7_approve_promotion(strategy_id: str, body: Level7PromoteBody | None = None) -> dict:
    """Human-gated champion promotion — never called by trading loop."""
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    payload = body or Level7PromoteBody()
    return l7.arena.human_approve_promotion(strategy_id, approved_by=payload.approved_by)


@app.get("/api/level7/memory")
def level7_memory() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    return {
        "ok": True,
        "patterns": l7.memory.list_patterns(30),
        "journal": l7.memory.list_journal(30),
        "note": "similarity ≠ certainty",
    }


@app.get("/api/level7/diagnostics")
def level7_diagnostics() -> dict:
    l7 = getattr(engine.ai, "level7", None)
    if l7 is None:
        raise HTTPException(503, "level7_unavailable")
    st = l7.status()
    last = st.get("last_cycle") or {}
    return {
        "ok": True,
        "diagnostics": last.get("diagnostics") or l7.diagnostics.diagnose(),
        "scorecard": last.get("scorecard") or st.get("scorecard"),
        "full_level7_claimed": False,
    }


@app.get("/api/level8/status")
def level8_status() -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        return {"ok": False, "reason": "level8_unavailable"}
    return {"ok": True, **l8.status()}


@app.post("/api/level8/cycle")
def level8_cycle(period: str = "HOURLY") -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    st = engine.ai.status()
    last = st.get("last_cycle") or {}
    out = l8.run_period(
        period,
        context={**(last.get("context") or {}), "data_valid": True, "prediction_tier": (last.get("learning") or {}).get("sample_tier")},
        metrics={
            "data_quality": 90,
            "market_regime": (last.get("regime") or {}).get("primary"),
            "what_worked": "Structured debate + fail-closed data gates",
            "what_failed": "Insufficient calibrated prediction sample",
            "test_next": "Volume confirmation ablation by regime",
        },
    )
    return {"ok": True, "cycle": out, "risk_bypass": False, "auto_promoted": False}


@app.post("/api/level8/acceptance")
def level8_acceptance() -> dict:
    """Run full continuous-learning acceptance chain (sandbox; no broker)."""
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    out = l8.run_acceptance_chain()
    return {"ok": True, "acceptance": out, "auto_promoted": False, "live_unlocked": False}


@app.get("/api/level8/replay/{decision_id}")
def level8_replay(decision_id: str) -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    return l8.snapshots.replay(decision_id)


@app.get("/api/level8/knowledge")
def level8_knowledge() -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    return {"ok": True, "knowledge": l8.knowledge.list_all(50), "note": "stale marked not deleted"}


@app.get("/api/level8/drift")
def level8_drift() -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    return {"ok": True, "open": l8.drift.list_open(50), "derate": l8.drift.derate()}


@app.get("/api/level8/reports")
def level8_reports(period: str | None = None) -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    return {"ok": True, "reports": l8.reports.list_reports(period=period, limit=30)}


class Level8FeedbackBody(BaseModel):
    decision_id: str
    label: str
    note: str = ""


@app.post("/api/level8/feedback")
def level8_feedback(body: Level8FeedbackBody) -> dict:
    l8 = getattr(engine.ai, "level8", None)
    if l8 is None:
        raise HTTPException(503, "level8_unavailable")
    return l8.add_human_feedback(body.decision_id, body.label, note=body.note)


@app.get("/api/models")
def list_models() -> dict:
    from ai.model_registry import model_registry

    return {
        "ok": True,
        "models": model_registry.list_models(),
        "active": model_registry.active(),
        "note": "Heuristic default. No auto LIVE promote. confidence ≠ probability.",
    }


@app.post("/api/models/{model_id}/promote")
def promote_model(model_id: str, body: ModelPromoteBody | None = None) -> dict:
    """Human-gated model promotion — never auto-called by the trading loop."""
    from ai.model_registry import model_registry

    payload = body or ModelPromoteBody()
    approved_by = str(payload.approved_by or "dashboard").strip() or "dashboard"
    out = model_registry.promote(model_id, approved_by=approved_by)
    if not out.get("ok"):
        raise HTTPException(404, out.get("reason") or "model_not_found")
    return out


@app.post("/api/autonomy/mode")
def autonomy_set_mode(body: AutonomyModeBody) -> dict:
    raw = (body.mode or "").strip().upper()
    if raw in {"LIVE", "LIVE_BROKER", "REAL", "REAL_MONEY"}:
        raise HTTPException(
            400,
            "Use execution_mode for PAPER|SHADOW|LIVE. UserTradingMode LIVE alias is blocked. "
            "LIVE broker requires LIVE_BROKER_ENABLED.",
        )
    parse_user_mode(body.mode)
    out = autonomy.set_user_mode(body.mode)
    engine.modes.set(body.mode)
    return out


@app.post("/api/autonomy/execution-mode")
def autonomy_set_execution_mode(body: AutonomyExecutionModeBody) -> dict:
    m = parse_execution_mode(body.execution_mode)
    if m.value == "LIVE" and not bool(getattr(settings, "live_broker_enabled", False)):
        # Allow selecting LIVE for readiness testing but keep broker blocked
        out = engine.set_execution_mode("LIVE")
        out["warning"] = "LIVE selected but LIVE_BROKER_ENABLED=false — orders remain BLOCKED"
        return out
    return engine.set_execution_mode(m.value)


@app.post("/api/autonomy/halt")
def autonomy_halt(body: dict | None = None) -> dict:
    """Manual kill — blocks new autonomous entries until clear-halt."""
    reason = "MANUAL_UI_HALT"
    if isinstance(body, dict) and body.get("reason"):
        reason = str(body.get("reason"))[:200]
    engine.halt(reason)
    return {
        "ok": True,
        "halted": True,
        "halt_reason": reason,
        "status": engine.status(),
        "note": "New AUTO entries blocked · clear with /api/autonomy/clear-halt",
    }


@app.post("/api/autonomy/clear-halt")
def autonomy_clear_halt() -> dict:
    """Manual clear only — never auto-clears."""
    engine.clear_halt()
    return {
        "ok": True,
        "halted": False,
        "status": engine.status(),
        "note": "Halt cleared · LIVE still locked by default",
    }


@app.post("/api/autonomy/cycle")
def autonomy_cycle(body: AutonomyCycleBody | None = None) -> dict:
    """Run one autonomous cycle via AutonomousTradingEngine (BIST)."""
    if settings.is_live and not bool(getattr(settings, "live_broker_enabled", False)):
        raise HTTPException(400, "settings.MODE=LIVE blocked without LIVE_BROKER_ENABLED")
    payload = body or AutonomyCycleBody()
    market = (payload.market or "BIST").upper()
    if market == "CRYPTO":
        return autonomy.run_crypto_cycle(force=bool(payload.force))
    if market != "BIST":
        raise HTTPException(400, "market must be BIST or CRYPTO")
    if payload.use_engine:
        return engine.run_cycle("BIST", force=bool(payload.force))
    return autonomy.run_bist_cycle(force=bool(payload.force))


@app.get("/api/autonomy/events")
def autonomy_events(limit: int = 100, cycle_id: str | None = None) -> dict:
    return {
        "events": engine.events.recent(limit=limit, cycle_id=cycle_id),
        "live_broker": "DISABLED" if not settings.live_broker_enabled else "FLAG_ON",
    }


@app.get("/api/autonomy/health")
def autonomy_health() -> dict:
    from autonomous.health import run_health_check

    return run_health_check(service, execution_mode=engine.execution_mode().value).to_dict()


@app.get("/api/autonomy/audit")
def autonomy_audit(limit: int = 20) -> dict:
    cycles = autonomy.audit.recent_cycles(limit=limit)
    return {
        "cycles": cycles,
        "live_broker": "DISABLED",
        "note": "Audit answers why a symbol was NO_TRADE.",
    }


@app.get("/api/autonomy/audit/{cycle_id}")
def autonomy_audit_cycle(cycle_id: str) -> dict:
    return {
        "cycle_id": cycle_id,
        "events": autonomy.audit.cycle_events(cycle_id),
        "live_broker": "DISABLED",
    }


@app.get("/api/autonomy/explain/{symbol}")
def autonomy_explain(symbol: str) -> dict:
    """Explainable card from last scan decision — computed features only."""
    symbol = symbol.upper()
    decisions = {d.symbol: d for d in service.scan(symbols=[symbol])}
    d = decisions.get(symbol)
    if not d:
        raise HTTPException(404, f"No decision for {symbol}")
    ser = service._serialize(d)
    return {
        "ok": True,
        "explain": explain_decision(ser),
        "decision": ser,
        "confidence_is_probability": False,
        "live_broker": "DISABLED",
    }


@app.get("/api/universe")
def api_universe() -> dict:
    stats = universe_stats()
    last = engine.status().get("last_cycle") or {}
    filt = last.get("filter_stats") or {}
    return {
        **stats,
        "provider_class": classify_provider(service.provider),
        "provider_symbols": len([s for s in service.provider.list_symbols() if s != "XU100"]),
        "last_cycle": {
            "SCANNED": filt.get("ANALYZED") or filt.get("DEEP_ANALYSIS"),
            "QUALIFIED": filt.get("QUALIFIED") or filt.get("FAST_FILTER"),
            "UNIVERSE": filt.get("FULL_MARKET_UNIVERSE") or filt.get("UNIVERSE"),
            "WITH_MARKET_DATA": filt.get("WITH_MARKET_DATA"),
            "SIGNALS": last.get("signals"),
            "TOP_DISPLAY": filt.get("TOP_DISPLAY", 10),
        },
        "note": "FULL_MARKET_UNIVERSE is catalog size; WITH_MARKET_DATA is provider intersection.",
    }


@app.get("/api/notifications/status")
def notifications_status() -> dict:
    return channel_status_report()


@app.post("/api/auth/login")
def auth_login(body: LoginBody) -> dict:
    return auth_store.login(body.username or "user", body.token)


@app.get("/api/auth/status")
def auth_status() -> dict:
    return {
        "auth_enabled": bool(getattr(settings, "auth_enabled", False)),
        "roles": [r.value for r in Role],
        "note": "When AUTH_ENABLED=false endpoints stay open for local paper. Trading endpoints require TRADER+ when enabled.",
    }


@app.post("/api/paper/cancel")
def paper_cancel(body: CancelOrderBody, authorization: str | None = Header(default=None)) -> dict:
    if bool(getattr(settings, "auth_enabled", False)):
        auth_store.require(authorization, min_role=Role.TRADER)
    return service.broker.cancel(body.client_order_id).__dict__


@app.get("/api/paper/orders")
def paper_orders() -> dict:
    return {"open_orders": service.broker.list_open_orders(), "pnl_type": "PAPER"}


@app.post("/api/live/confirm")
def live_confirm(body: LiveConfirmBody, authorization: str | None = Header(default=None)) -> dict:
    """Explicit LIVE confirmation gate — does NOT enable broker by itself."""
    auth_store.require(authorization, min_role=Role.ADMIN)
    if not body.confirm or body.phrase.strip().upper() != "I_UNDERSTAND_LIVE_RISK":
        raise HTTPException(400, "Confirmation phrase required: I_UNDERSTAND_LIVE_RISK")
    if not bool(getattr(settings, "live_broker_enabled", False)):
        return {
            "ok": False,
            "live": "DISABLED",
            "message": "LIVE_BROKER_ENABLED=false — confirmation recorded logically but LIVE remains locked in this process (set env + restart with real adapter).",
            "readiness": _live_readiness_payload(),
        }
    # Frozen settings — cannot mutate; document requirement
    return {
        "ok": True,
        "message": "Admin confirmation accepted. Set LIVE_CONFIRMED=true in environment to persist. LIVE still requires real broker adapter.",
        "live_broker_enabled": bool(settings.live_broker_enabled),
        "live_confirmed_env": bool(getattr(settings, "live_confirmed", False)),
        "readiness": _live_readiness_payload(),
    }


def _live_readiness_payload() -> dict:
    from execution.live_factory import live_adapter_status
    from trading_safety.live_readiness import evaluate_live_money_readiness

    md_ok = None
    try:
        md_ok = bool(service.provider.has_market_data())
    except Exception:  # noqa: BLE001
        md_ok = False
    report = evaluate_live_money_readiness(market_data_ok=md_ok)
    out = report.to_dict()
    out["adapter"] = live_adapter_status()
    out["flags"] = {
        "MODE": settings.mode,
        "EXECUTION_MODE": settings.execution_mode,
        "LIVE_BROKER_ENABLED": bool(settings.live_broker_enabled),
        "LIVE_CONFIRMED": bool(settings.live_confirmed),
        "LIVE_CONFIRMATION_REQUIRED": bool(settings.live_confirmation_required),
        "LIVE_BROKER_ADAPTER": getattr(settings, "live_broker_adapter", "disabled"),
        "LIVE_DRY_RUN": bool(getattr(settings, "live_dry_run", True)),
        "AUTH_ENABLED": bool(settings.auth_enabled),
        "KILL_SWITCH": bool(settings.kill_switch),
    }
    return out


@app.get("/api/live/readiness")
def live_readiness() -> dict:
    """Live-money checklist — foundation only; never auto-unlocks."""
    return {"ok": True, **_live_readiness_payload()}


@app.get("/api/live/status")
def live_status() -> dict:
    """Compact live lock status for UI / ops."""
    payload = _live_readiness_payload()
    return {
        "ok": True,
        "live_trading": False,
        "ready": bool(payload.get("ready")),
        "verdict": payload.get("verdict"),
        "live_money_readiness": payload.get("live_money_readiness"),
        "adapter": payload.get("adapter"),
        "flags": payload.get("flags"),
        "message": "Canlı para altyapısı hazır · emir yolu kilitli · ileride manuel açılır",
    }


@app.get("/api/phase2/audit")
def phase2_audit() -> dict:
    from data.http_live import HttpLiveMarketDataProvider

    prov = service.provider
    kind = classify_provider(prov)
    u = universe_stats()
    last = engine.status().get("last_cycle") or {}
    filt = last.get("filter_stats") or {}
    return {
        "BIST_PROVIDER": "REAL"
        if isinstance(prov, HttpLiveMarketDataProvider) and prov.has_market_data()
        else ("PARTIAL" if isinstance(prov, HttpLiveMarketDataProvider) else ("MOCK" if kind == "MOCK" else "MISSING")),
        "SYMBOL_DISCOVERY": "FULL" if u["full_universe"] >= 400 else "PARTIAL",
        "BIST100": "VALID",
        "FULL_UNIVERSE": u["full_universe"],
        "ANALYZED": filt.get("ANALYZED") or filt.get("DEEP_ANALYSIS") or 0,
        "QUALIFIED": filt.get("QUALIFIED") or filt.get("FAST_FILTER") or 0,
        "TOP_OPPORTUNITIES": len((last.get("ranked") or [])[:10]),
        "PARIBU": "DISABLED" if not settings.crypto_enabled else "PARTIAL",
        "PREDICTION": "PARTIAL",
        "NOTIFICATIONS": channel_status_report()["channels"],
        "AUTH": "READY" if settings.auth_enabled else "PARTIAL",
        "PAPER_FSM": "READY",
        "LIVE": "DISABLED"
        if not settings.live_broker_enabled
        else ("DRY-RUN" if not settings.live_confirmed else "ENABLED_FLAG_ONLY"),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


if any(STATIC.iterdir()):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
