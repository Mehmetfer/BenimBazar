"""Daily trading dashboard assembly — LESS DATA, MORE DECISION."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config.models import utc_now
from data.integrity import DataSourceMeta, FreshnessStatus, format_age_tr


# Display rank (lower = higher on screen). Favorites boost within same bucket only.
SIGNAL_RANK = {
    "STRONG_BUY": 1,
    "BUY": 2,
    "AL": 2,
    "WAIT_FOR_ENTRY": 3,
    "BREAKOUT": 4,
    "WATCH": 5,
    "WAIT": 6,
    "HOLD": 6,
    "BEKLE": 6,
    "SELL": 7,
    "SAT": 7,
    "STRONG_SELL": 8,
    "NO_TRADE": 9,
    "ALMA": 9,
    "AVOID": 9,
}


def opportunity_score(item: dict[str, Any]) -> float:
    """0–100 daily trading opportunity from real computed fields only."""
    dec = (item.get("final_decision") or item.get("decision") or item.get("signal") or "").upper()
    conf = float(item.get("ai_confidence") or 0)
    ev = float((item.get("opportunity") or {}).get("expected_value") or 0)
    rr = float(
        (item.get("ai_trade_plan") or {}).get("risk_reward")
        or (item.get("trade_plan") or {}).get("risk_reward")
        or 0
    )
    mom = float((item.get("factors") or {}).get("momentum") or 50)
    liq_ok = 1.0 if item.get("universe_ok", True) else 0.0
    base = {
        "STRONG_BUY": 88,
        "BUY": 72,
        "AL": 72,
        "WAIT_FOR_ENTRY": 65,
        "WATCH": 48,
        "WAIT": 40,
        "BEKLE": 40,
        "SELL": 35,
        "SAT": 35,
        "STRONG_SELL": 30,
        "NO_TRADE": 15,
        "ALMA": 15,
    }.get(dec, 40)
    score = (
        base * 0.35
        + conf * 0.25
        + min(100.0, max(0.0, (ev + 1) * 40)) * 0.15
        + min(100.0, rr * 30) * 0.15
        + mom * 0.07
        + liq_ok * 100 * 0.03
    )
    # Confirmation gate: weak confirmation cannot reach STRONG tier display score
    conf_score = float(item.get("confirmation_score") or 0)
    if dec == "STRONG_BUY" and conf_score < 70:
        score = min(score, 74)
        item["_demoted_strong"] = True
    return round(max(0.0, min(100.0, score)), 1)


def sort_key(item: dict[str, Any]) -> tuple:
    dec = (item.get("final_decision") or item.get("decision") or item.get("signal") or "").upper()
    rank = SIGNAL_RANK.get(dec, 50)
    fav = 0 if item.get("is_favorite") else 1
    # Favorites first within same signal strength only — never lift weak above strong
    opp = -float(item.get("opportunity_score") or 0)
    ev = -float((item.get("opportunity") or {}).get("expected_value") or 0)
    rr = -float(
        (item.get("ai_trade_plan") or {}).get("risk_reward")
        or (item.get("trade_plan") or {}).get("risk_reward")
        or 0
    )
    conf = -float(item.get("ai_confidence") or 0)
    return (rank, fav, opp, ev, rr, conf)


def signal_expired(item: dict[str, Any], ttl_sec: float, now: datetime | None = None) -> bool:
    ts = item.get("signal_timestamp") or item.get("quote_ts")
    if not ts:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (now - t).total_seconds() > ttl_sec


def confirmation_score(item: dict[str, Any]) -> float:
    """Multi-factor confirmation before STRONG BUY display (0–100)."""
    ind = item.get("indicators") or {}
    pa = item.get("price_action") or {}
    mtf = item.get("mtf") or {}
    score = 0.0
    # Trend
    if (item.get("trend") or "").upper() in {"UP", "BULL", "YUKSELIS", "BULLISH"}:
        score += 15
    elif "HH" in str((item.get("indicators") or {}).get("structure") or ""):
        score += 12
    # Momentum / RSI
    rsi = float(ind.get("rsi") or 50)
    if 50 <= rsi <= 70:
        score += 12
    elif 45 <= rsi < 50:
        score += 6
    # Volume
    if pa.get("volume_confirmed"):
        score += 15
    # Volatility / ATR present
    if float(ind.get("atr") or 0) > 0:
        score += 8
    # VWAP / price above mid
    if float(ind.get("ema21") or 0) and float(item.get("price") or item.get("price") or 0):
        # use ema21 as proxy if vwap not in indicators
        score += 8
    # Structure / S-R
    if not pa.get("false_breakout"):
        score += 10
    # Regime
    regime = (item.get("regime") or "").upper()
    if regime in {"BULL", "STRONG_BULL"}:
        score += 12
    elif regime == "NEUTRAL":
        score += 5
    # Liquidity / universe
    if item.get("universe_ok"):
        score += 10
    # MTF alignment
    bulls = sum(1 for v in mtf.values() if str(v).upper() in {"BULL", "UP"})
    if bulls >= 3:
        score += 10
    return round(min(100.0, score), 1)


def risk_label(item: dict[str, Any]) -> str:
    r = (item.get("risk") or "").upper()
    if r in {"LOW", "DUSUK", "DÜŞÜK"}:
        return "Düşük"
    if r in {"HIGH", "YUKSEK", "YÜKSEK", "EXTREME"}:
        return "Yüksek"
    # Derive from R/R and stop distance when explicit missing
    rr = float(
        (item.get("ai_trade_plan") or {}).get("risk_reward")
        or (item.get("trade_plan") or {}).get("risk_reward")
        or 0
    )
    if rr >= 2.5:
        return "Düşük"
    if rr >= 1.5:
        return "Orta"
    return "Yüksek"


def simplify_card(item: dict[str, Any], source: DataSourceMeta) -> dict[str, Any]:
    """Main-screen card: only decision-critical fields + integrity labels."""
    ap = item.get("ai_trade_plan") or {}
    tp = item.get("trade_plan") or {}
    z = ap.get("entry_zone") or {}
    dec = (item.get("final_decision") or item.get("decision") or item.get("signal") or "").upper()
    forecasts = item.get("ai_forecast") or []
    short_fc = [f for f in forecasts if f.get("horizon") in {"1H", "3H", "1D"}]
    rel = item.get("ai_reliability") or {}
    entry = None
    if z.get("low") is not None:
        entry = f"{z.get('low')} – {z.get('high')}"
    elif tp.get("entry") is not None:
        entry = str(tp.get("entry"))

    # Stale / no-data: strip actionable trade fields
    show_prices = source.kind.value == "SIMULATED" or source.is_live_market
    if source.freshness in {FreshnessStatus.NO_DATA, FreshnessStatus.DISCONNECTED} or not show_prices:
        return {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "is_favorite": bool(item.get("is_favorite")),
            "decision": "NO_DATA",
            "decision_label": "VERİ YOK",
            "price": None,
            "change_pct": None,
            "price_label": source.price_label,
            "data_status": source.freshness.value,
            "data_source_kind": source.kind.value,
            "tradeable": False,
            "ui_status": "⚠ DATA UNAVAILABLE",
            "note": source.note,
            "sources": {
                "price": source.display_name,
                "ai": "Model Analysis",
            },
        }

    plan_invalid = bool(item.get("plan_invalid"))
    return {
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "is_favorite": bool(item.get("is_favorite")),
        "decision": dec,
        "decision_label": _label_tr(dec),
        "price": item.get("price") if show_prices else None,
        "prev_close": item.get("prev_close"),
        "change_pct": item.get("change_pct"),
        "price_label": source.price_label,
        "live_price_label": "CANLI FİYAT" if source.is_live_market else source.price_label,
        "prev_close_label": "ÖNCEKİ KAPANIŞ",
        "entry": None if plan_invalid else entry,
        "stop": None if plan_invalid else (ap.get("stop_loss") if ap else tp.get("stop") or item.get("stop_price")),
        "targets": None
        if plan_invalid
        else [
            (ap.get("target1") or {}).get("price") if isinstance(ap.get("target1"), dict) else tp.get("target1"),
            (ap.get("target2") or {}).get("price") if isinstance(ap.get("target2"), dict) else tp.get("target2"),
            (ap.get("target3") or {}).get("price") if isinstance(ap.get("target3"), dict) else tp.get("target3"),
        ],
        "risk_reward": None
        if plan_invalid
        else (ap.get("risk_reward") if ap else tp.get("risk_reward")),
        "ai_confidence": item.get("ai_confidence"),  # TAHMİN OLASILIĞI / confidence
        "historical_accuracy": rel.get("gecmis_dogruluk"),  # GEÇMİŞ DOĞRULUK — distinct
        "confidence_label": "AI Güven",
        "accuracy_label": "AI Geçmiş Doğruluk",
        "opportunity_score": item.get("opportunity_score"),
        "confirmation_score": item.get("confirmation_score"),
        "risk_label": risk_label(item),
        "time_horizon": "INTRADAY",
        "signal_timestamp": item.get("signal_timestamp"),
        "quote_ts": item.get("quote_ts"),
        "data_status": source.freshness.value,
        "data_age": format_age_tr(source.age_seconds),
        "data_source_kind": source.kind.value,
        "tradeable": bool(source.is_live_market and source.kind.value in {"LIVE", "DELAYED", "BROKER"}),
        "ui_status": (
            "● LIVE"
            if source.is_live_market
            else ("◐ SIMULATED" if source.kind.value == "SIMULATED" else "⚠ DATA UNAVAILABLE")
        ),
        "plan_invalid": plan_invalid,
        "plan_note": item.get("plan_note"),
        "forecast_short": short_fc,
        "ai_reliability_grade": rel.get("overall_grade"),
        "sector": item.get("sector"),
        "sources": {
            "price": source.display_name,
            "kind": source.kind.value,
            "news": item.get("news_source") or "UNAVAILABLE",
            "kap": item.get("kap_source") or "UNAVAILABLE",
            "fundamental": item.get("fundamental_source") or "UNKNOWN",
            "ai": "Model Analysis",
        },
        "metric_note": "AI Güven ≠ AI Geçmiş Doğruluk. Kâr garantisi yok.",
    }


def _label_tr(dec: str) -> str:
    return {
        "STRONG_BUY": "GÜÇLÜ AL",
        "BUY": "AL",
        "AL": "AL",
        "WAIT_FOR_ENTRY": "GİRİŞ BEKLE",
        "WATCH": "İZLE",
        "WAIT": "BEKLE",
        "BEKLE": "BEKLE",
        "HOLD": "BEKLE",
        "SELL": "SAT",
        "SAT": "SAT",
        "STRONG_SELL": "GÜÇLÜ SAT",
        "NO_TRADE": "İŞLEM YOK",
        "ALMA": "İŞLEM YOK",
    }.get(dec, dec)


def build_daily_home(
    universe: list[dict[str, Any]],
    source: DataSourceMeta,
    *,
    signal_ttl_sec: float = 3600,
    top_n: int = 8,
    signals_paused: bool = False,
) -> dict[str, Any]:
    """Assemble main screen sections with integrity + ranking rules."""
    now = utc_now()
    enriched: list[dict[str, Any]] = []
    for raw in universe:
        item = dict(raw)
        item["confirmation_score"] = confirmation_score(item)
        # Demote unconfirmed STRONG_BUY
        dec = (item.get("final_decision") or item.get("decision") or "").upper()
        if dec == "STRONG_BUY" and item["confirmation_score"] < 70:
            item["final_decision"] = "BUY"
            item["decision"] = "BUY"
            item["demoted_from_strong"] = True
        if signal_expired(item, signal_ttl_sec, now):
            item["final_decision"] = "WAIT"
            item["decision"] = "WAIT"
            item["signal_expired"] = True
        # Stale real data → no new strong signals
        if source.freshness == FreshnessStatus.STALE or signals_paused:
            if (item.get("final_decision") or "").upper() in {"STRONG_BUY", "BUY", "AL", "STRONG_SELL", "SELL", "SAT"}:
                item["final_decision"] = "WAIT"
                item["decision"] = "WAIT"
                item["paused_reason"] = "STALE_OR_DISCONNECTED"
        item["opportunity_score"] = opportunity_score(item)
        # Entry zone chase: if price left entry band materially, invalidate plan display
        ap = item.get("ai_trade_plan") or {}
        z = ap.get("entry_zone") or {}
        px = item.get("price")
        if px and z.get("low") is not None and z.get("high") is not None:
            lo, hi = float(z["low"]), float(z["high"])
            band = max(0.01, hi - lo)
            if px > hi + band * 0.5 or px < lo - band * 0.5:
                item["plan_invalid"] = True
                item["plan_note"] = "Eski giriş bölgesi geçersiz. Yeni setup gerekir."
        enriched.append(item)

    enriched.sort(key=sort_key)
    cards = [simplify_card(x, source) for x in enriched]

    def take(pred, limit: int | None = None):
        out = [c for c in cards if pred(c)]
        return out[:limit] if limit else out

    strong = take(lambda c: c.get("decision") == "STRONG_BUY", top_n)
    buys = take(lambda c: c.get("decision") in {"BUY", "AL"}, top_n)
    waits = take(lambda c: c.get("decision") in {"WAIT", "WATCH", "BEKLE", "HOLD", "WAIT_FOR_ENTRY"}, 5)
    sells = take(lambda c: c.get("decision") in {"SELL", "SAT", "STRONG_SELL"}, 5)
    favs = take(lambda c: c.get("is_favorite"), 12)
    fav_strong = [c for c in favs if c.get("decision") in {"STRONG_BUY", "BUY", "AL"}]

    actionable = strong + buys
    no_opportunity = len(actionable) == 0 or signals_paused or source.freshness in {
        FreshnessStatus.NO_DATA,
        FreshnessStatus.DISCONNECTED,
    }

    return {
        "principle": "LESS DATA, MORE DECISION · HER GÜN İŞLEM YOK — EN İYİ RİSK/GETİRİ",
        "focus": "INTRADAY",
        "timeframes": {"primary": ["5M", "15M", "30M", "1H"], "support": ["4H", "1D"]},
        "market": {
            "exchange": "BIST",
            "session": source.market_session.value,
            "session_label": "PİYASA AÇIK" if source.market_session.value == "OPEN" else "PİYASA KAPALI",
            "last_update": source.last_update,
            "last_update_ago": format_age_tr(source.age_seconds),
            "data_status": source.freshness.value,
            "price_label": source.price_label,
            "provider": source.display_name,
            "connected": source.connected,
            "is_live_market": source.is_live_market,
            "live_ready": source.live_ready,
            "note": source.note,
        },
        "integrity": source.to_dict(),
        "signals_paused": signals_paused,
        "no_opportunity": no_opportunity,
        "no_opportunity_message": (
            "⚠ CANLI VERİ BAĞLANTISI KESİLDİ — sinyaller PAUSED"
            if signals_paused
            else (
                "DATA SOURCE REQUIRED — canlı veri yok"
                if source.kind.value in {"REQUIRED", "UNAVAILABLE"}
                else "ŞU AN İŞLEM FIRSATI YOK"
            )
        ),
        "sections": {
            "favorites": favs,
            "favorites_opportunities": fav_strong,
            "strong_buy": strong,
            "buy": buys,
            "wait": waits,
            "sell": sells,
            "top_opportunities": (strong + buys)[:top_n],
        },
        "counts": {
            "strong_buy": len(strong),
            "buy": len(buys),
            "wait": len(waits),
            "sell": len(sells),
            "favorites": len(favs),
            "universe": len(cards),
        },
        "filters": ["Tümü", "Favoriler", "Güçlü AL", "AL", "Bekle", "Sat"],
        "generated_at": now.isoformat(),
    }
