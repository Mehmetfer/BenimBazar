from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PostTradeReview:
    symbol: str
    pnl: float
    won: bool
    lessons: list[str]


def review_closed_trade(
    *,
    symbol: str,
    pnl: float,
    entry_reason: str,
    regime_at_entry: str,
    regime_at_exit: str,
    stop_distance_pct: float,
    news_flag: str | None = None,
) -> PostTradeReview:
    lessons = []
    won = pnl >= 0
    if won:
        lessons.append("winner — review if partial TP left edge on table")
        if "volume" in entry_reason.lower():
            lessons.append("volume confirmation likely helped")
    else:
        lessons.append("loser — verify stop was structure-based not arbitrary")
        if stop_distance_pct < 1.0:
            lessons.append("stop may have been too tight vs noise")
        lessons.append("do not add to loser / no revenge trade")
    if regime_at_entry != regime_at_exit:
        lessons.append(f"regime shifted {regime_at_entry}->{regime_at_exit}")
    if news_flag:
        lessons.append(f"news_context={news_flag}")
    lessons.append("no look-ahead: only entry-time info counts for process review")
    return PostTradeReview(symbol=symbol, pnl=pnl, won=won, lessons=lessons)


@dataclass
class DriftAlert:
    defensive: bool
    reason: str


def detect_model_drift(*, recent_hit_rate: float, baseline_hit_rate: float, recent_avg_ev: float) -> DriftAlert:
    """If live/paper edge decays, recommend DEFENSIVE — never auto-deploy new strategies."""
    if recent_hit_rate < baseline_hit_rate - 0.15 or recent_avg_ev < 0:
        return DriftAlert(True, "edge_decay_defensive")
    return DriftAlert(False, "stable")
