"""Crypto dashboard cards — UI projection only (no broker execution)."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from crypto.market import MarketType
from crypto.symbols import to_display_symbol
from data.integrity import age_seconds, format_age_tr

# Favorites first, then signal strength (user requirement)
_SIGNAL_SORT: dict[str, int] = {
    "STRONG_BUY": 0,
    "BUY": 1,
    "AL": 1,
    "WAIT": 2,
    "WATCH": 2,
    "BEKLE": 2,
    "HOLD": 2,
    "WAIT_FOR_ENTRY": 2,
    "SELL": 3,
    "SAT": 3,
    "STRONG_SELL": 4,
    "NO_TRADE": 5,
    "ALMA": 5,
    "NO_DATA": 6,
}

_SIGNAL_LABEL: dict[str, str] = {
    "STRONG_BUY": "Güçlü AL",
    "BUY": "AL",
    "AL": "AL",
    "WAIT": "Bekle",
    "WATCH": "İzle",
    "BEKLE": "Bekle",
    "HOLD": "Bekle",
    "WAIT_FOR_ENTRY": "Giriş bekle",
    "SELL": "Sat",
    "SAT": "Sat",
    "STRONG_SELL": "Güçlü SAT",
    "NO_TRADE": "İşlem yok",
    "ALMA": "Alma",
    "NO_DATA": "Veri yok",
}


def live_status_badge(
    *,
    has_quote: bool,
    data_source_kind: str | None,
    ts,
    max_age_sec: float | None = None,
) -> str:
    """UI freshness badge: LIVE | STALE | UNAVAILABLE."""
    if not has_quote:
        return "UNAVAILABLE"
    kind = (data_source_kind or "").upper()
    if kind in {"REQUIRED", "UNAVAILABLE", "UNKNOWN", ""}:
        return "UNAVAILABLE"
    if kind not in {"LIVE", "DELAYED"}:
        # Simulated/test must never show as LIVE
        if kind in {"SIMULATED", "TEST", "BACKTEST", "MOCK"}:
            return "UNAVAILABLE"
        return "UNAVAILABLE"
    age = age_seconds(ts)
    max_age = float(max_age_sec if max_age_sec is not None else settings.data_freshness_sec)
    if age is None:
        return "UNAVAILABLE"
    if age > max_age:
        return "STALE"
    return "LIVE"


def signal_sort_rank(signal: str) -> int:
    return _SIGNAL_SORT.get((signal or "").upper(), 9)


def sort_dashboard_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """FAVORITES → STRONG BUY → BUY → WAIT → SELL → STRONG SELL."""

    def key(r: dict[str, Any]) -> tuple:
        fav = 0 if r.get("is_favorite") else 1
        pri = -int(r.get("favorite_priority") or 0) if r.get("is_favorite") else 0
        sig = signal_sort_rank(str(r.get("signal") or r.get("decision") or ""))
        score = -float(r.get("model_score") or r.get("confidence") or 0)
        return (fav, sig, pri, score, str(r.get("symbol") or ""))

    return sorted(rows, key=key)


def card_from_parts(
    *,
    symbol: str,
    price: float | None,
    change_pct: float | None,
    volume: float | None,
    signal: str,
    model_score: float | None,
    entry: float | None,
    stop: float | None,
    target: float | None,
    risk_reward: float | None,
    trend: str | None,
    last_update,
    live_status: str,
    is_favorite: bool = False,
    favorite_priority: int = 0,
    note: str = "",
    data_source_kind: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    sig = (signal or "NO_DATA").upper()
    age = age_seconds(last_update)
    return {
        "market_type": MarketType.CRYPTO.value,
        "symbol": symbol,
        "display": to_display_symbol(symbol),
        "coin": to_display_symbol(symbol),
        "price": price,
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "volume": volume,
        "signal": sig,
        "decision": sig,
        "decision_label": _SIGNAL_LABEL.get(sig, sig),
        "confidence": round(float(model_score), 1) if model_score is not None else None,
        "model_score": round(float(model_score), 1) if model_score is not None else None,
        "confidence_label": "Model Skoru",
        "entry": entry,
        "stop": stop,
        "target": target,
        "targets": [t for t in [target] if t is not None],
        "risk_reward": risk_reward,
        "trend": trend or "—",
        "last_update": last_update.isoformat() if hasattr(last_update, "isoformat") and last_update else None,
        "last_update_ago": format_age_tr(age),
        "live_status": live_status,
        "data_status": live_status,
        "is_favorite": bool(is_favorite),
        "favorite_priority": int(favorite_priority or 0),
        "note": note,
        "data_source_kind": data_source_kind,
        "provider": provider,
        "paper_only": True,
        "live_trading": False,
    }


def sectionize(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    favs = [r for r in rows if r.get("is_favorite")]
    strong = [r for r in rows if r.get("signal") == "STRONG_BUY" and not r.get("is_favorite")]
    buy = [r for r in rows if r.get("signal") in {"BUY", "AL"} and not r.get("is_favorite")]
    wait = [
        r
        for r in rows
        if r.get("signal") in {"WAIT", "WATCH", "BEKLE", "HOLD", "WAIT_FOR_ENTRY"} and not r.get("is_favorite")
    ]
    sell = [r for r in rows if r.get("signal") in {"SELL", "SAT"} and not r.get("is_favorite")]
    strong_sell = [r for r in rows if r.get("signal") == "STRONG_SELL" and not r.get("is_favorite")]
    return {
        "favorites": favs,
        "strong_buy": strong,
        "buy": buy,
        "wait": wait,
        "sell": sell,
        "strong_sell": strong_sell,
        "all": rows,
    }
