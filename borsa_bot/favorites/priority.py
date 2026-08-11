from __future__ import annotations

from config.models import MarketRegime, SignalAction
from favorites.models import FavoriteSort, ScannerClass


def signal_strength(decision: str, signal: str) -> float:
    d = (decision or signal or "").upper()
    table = {
        "STRONG_BUY": 100,
        "BUY": 80,
        "AL": 80,
        "BREAKOUT": 75,
        "WATCH": 55,
        "WAIT": 40,
        "WAIT_FOR_ENTRY": 50,
        "BEKLE": 40,
        "HOLD": 45,
        "REDUCE": 35,
        "SELL": 70,
        "SAT": 70,
        "STRONG_SELL": 90,
        "NO_TRADE": 10,
        "ALMA": 10,
    }
    return float(table.get(d, 30))


def regime_boost(regime: MarketRegime | str, side: str = "BUY") -> float:
    r = regime.value if isinstance(regime, MarketRegime) else str(regime)
    if side == "SELL":
        return {"STRONG_BEAR": 18, "BEAR": 12, "NEUTRAL": 4, "BULL": 0, "STRONG_BULL": -4}.get(r, 0)
    return {"STRONG_BULL": 18, "BULL": 12, "NEUTRAL": 4, "BEAR": -6, "STRONG_BEAR": -14}.get(r, 0)


def compute_priority_score(
    *,
    is_favorite: bool,
    decision: str,
    signal: str,
    ai_confidence: float,
    expected_value: float | None,
    risk_reward: float | None,
    momentum: float | None,
    regime: MarketRegime | str,
    watchlist_priority: int = 50,
    breakout: bool = False,
) -> float:
    """Weighted composite — NOT a simple average. Favorite ≠ BUY advantage.

    Favorites only get a visibility/queue boost via watchlist_priority term,
    never an artificial decision upgrade.
    """
    ss = signal_strength(decision, signal)
    if breakout and ss < 75:
        ss = max(ss, 72)
    conf = max(0.0, min(100.0, float(ai_confidence)))
    ev = float(expected_value or 0.0)
    # Map EV roughly to 0-100 contribution (cap)
    ev_term = max(-20.0, min(40.0, ev * 80.0))
    rr = float(risk_reward or 0.0)
    rr_term = 0.0
    if rr >= 3:
        rr_term = 22
    elif rr >= 2:
        rr_term = 16
    elif rr >= 1.5:
        rr_term = 10
    elif rr > 0:
        rr_term = 2
    mom = max(0.0, min(100.0, float(momentum if momentum is not None else 50)))
    reg = regime_boost(regime, side="SELL" if str(decision).upper() in {"SELL", "STRONG_SELL", "SAT"} else "BUY")
    wl = max(0, min(100, int(watchlist_priority))) * (0.25 if is_favorite else 0.0)

    # Non-equal weights emphasizing edge quality over membership
    score = (
        ss * 0.28
        + conf * 0.22
        + (50 + ev_term) * 0.18
        + rr_term * 1.2  # already scaled
        + mom * 0.12
        + (50 + reg) * 0.10
        + wl * 0.10
    )
    # Soft favorite visibility nudge only (does not flip NO_TRADE → BUY)
    if is_favorite:
        score += 4.0
    return round(max(0.0, min(100.0, score)), 2)


def sort_rank_key(item: dict, sort: FavoriteSort) -> tuple:
    """Lower tuple sorts first when used with reverse=False — we use reverse=True for most."""
    ap = item.get("ai_trade_plan") or {}
    opp = item.get("opportunity") or {}
    factors = item.get("factors") or {}
    if sort == FavoriteSort.ALPHABETICAL:
        return (0, item.get("symbol") or "")
    if sort == FavoriteSort.CONFIDENCE:
        return (float(item.get("ai_confidence") or 0),)
    if sort == FavoriteSort.PRICE_CHANGE:
        return (float(item.get("change_pct") or 0),)
    if sort == FavoriteSort.MOMENTUM:
        return (float(factors.get("momentum") or item.get("scores", {}).get("momentum") or 0),)
    if sort == FavoriteSort.EXPECTED_RETURN:
        return (float(opp.get("expected_return_pct") or ap.get("expected_return_pct") or 0),)
    if sort == FavoriteSort.RISK_REWARD:
        return (float((item.get("trade_plan") or {}).get("risk_reward") or ap.get("risk_reward") or 0),)
    if sort == FavoriteSort.SIGNAL_STRENGTH:
        return (signal_strength(item.get("decision") or "", item.get("signal") or ""),)
    if sort == FavoriteSort.AI_SCORE:
        return (float((item.get("scores") or {}).get("final") or item.get("buy_score") or 0),)
    # default PRIORITY
    return (float(item.get("priority_score") or 0),)


def display_priority_bucket(item: dict) -> int:
    """Main-page ordering buckets (lower = higher on page)."""
    fav = bool(item.get("is_favorite"))
    d = (item.get("decision") or item.get("signal") or "").upper()
    pa = item.get("price_action") or {}
    breakout = bool(pa.get("pattern") == "BREAKOUT" or pa.get("breakout"))
    if fav and d in {"STRONG_BUY"}:
        return 1
    if fav and d in {"BUY", "AL"}:
        return 2
    if fav and breakout:
        return 3
    if fav and d in {"WATCH", "WAIT_FOR_ENTRY"}:
        return 4
    if fav and d in {"SELL", "STRONG_SELL", "SAT"}:
        return 5
    if d in {"STRONG_BUY", "BUY", "AL"} and float(item.get("priority_score") or 0) >= 70:
        return 6
    if fav:
        return 7
    return 8


def classify_scanner(decision: str, risk_verdict: str, priority_score: float, chase: bool) -> ScannerClass:
    d = (decision or "").upper()
    if risk_verdict == "REJECT" or d in {"NO_TRADE", "ALMA"}:
        return ScannerClass.NO_TRADE
    if d in {"STRONG_SELL", "SELL", "SAT"}:
        return ScannerClass.RISK
    if chase or d in {"WAIT", "WAIT_FOR_ENTRY", "BEKLE"}:
        return ScannerClass.WAIT
    if d == "STRONG_BUY" and priority_score >= 75:
        return ScannerClass.STRONG_OPPORTUNITY
    if d in {"BUY", "AL"} and priority_score >= 60:
        return ScannerClass.OPPORTUNITY
    if d in {"WATCH"}:
        return ScannerClass.WAIT
    if priority_score < 40:
        return ScannerClass.RISK
    return ScannerClass.WAIT
