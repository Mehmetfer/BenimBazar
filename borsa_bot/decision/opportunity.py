"""Phase 2 — Opportunity discovery & competitive ranking (reuse scan outputs)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ENTRY_LIKE = {"STRONG_BUY", "BUY", "AL"}
EXIT_LIKE = {"STRONG_SELL", "SELL", "SAT"}


@dataclass
class RankedOpportunity:
    symbol: str
    market_type: str
    action: str
    opportunity_score: float
    model_score: float | None
    expected_value: float | None
    expected_return_pct: float | None
    expected_risk_pct: float | None
    risk_reward: float | None
    confidence: float | None
    regime: str | None
    mtf: dict[str, Any] = field(default_factory=dict)
    liquidity_ok: bool = True
    spread_ok: bool = True
    is_favorite: bool = False
    rank: int = 0
    why_better: list[str] = field(default_factory=list)
    why_worse: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ranked_from_dict(d: dict[str, Any]) -> RankedOpportunity:
    fields = RankedOpportunity.__dataclass_fields__
    kwargs = {k: d[k] for k in fields if k in d}
    # required minimums
    kwargs.setdefault("symbol", str(d.get("symbol") or "?"))
    kwargs.setdefault("market_type", str(d.get("market_type") or "BIST"))
    kwargs.setdefault("action", str(d.get("action") or "WAIT"))
    kwargs.setdefault("opportunity_score", float(d.get("opportunity_score") or 0))
    for opt in (
        "model_score",
        "expected_value",
        "expected_return_pct",
        "expected_risk_pct",
        "risk_reward",
        "confidence",
        "regime",
    ):
        kwargs.setdefault(opt, d.get(opt))
    return RankedOpportunity(**kwargs)


def _f(row: dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


def opportunity_score_from_row(row: dict[str, Any]) -> float:
    """Composite score for ranking — NOT trading permission."""
    base = _f(row, "priority_score", "opportunity_score", "buy_score", "ai_confidence", default=0.0) or 0.0
    opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
    ev = _f(opp, "expected_value", default=None)
    if ev is None:
        ev = _f(row, "expected_value", default=0.0) or 0.0
    rr = _f(opp, "risk_reward", default=None)
    if rr is None:
        rr = _f(row, "risk_reward", default=1.0) or 1.0
    liq = 0.0
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    if scores:
        liq = float(scores.get("liquidity") or 0) / 100.0
    fav = 5.0 if row.get("is_favorite") else 0.0
    action = str(row.get("final_decision") or row.get("decision") or row.get("signal") or "").upper()
    action_boost = {"STRONG_BUY": 12, "BUY": 8, "AL": 8, "WAIT": 0, "SELL": -4, "STRONG_SELL": -8}.get(action, 0)
    # Negative EV heavily demotes
    ev_term = max(-20.0, min(20.0, float(ev) * 4.0))
    return round(base + fav + action_boost + ev_term + min(8.0, rr * 2) + liq * 5, 2)


def rank_opportunities(
    rows: list[dict[str, Any]],
    *,
    market_type: str = "BIST",
    top_n: int = 10,
) -> list[RankedOpportunity]:
    scored: list[RankedOpportunity] = []
    for row in rows:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        action = str(row.get("final_decision") or row.get("decision") or row.get("signal") or "WAIT").upper()
        opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        mtf = row.get("mtf") if isinstance(row.get("mtf"), dict) else {}
        spread = _f(row, "spread_pct", default=None)
        spread_ok = True if spread is None else spread <= float(row.get("max_spread_pct") or 2.0)
        scored.append(
            RankedOpportunity(
                symbol=sym,
                market_type=market_type,
                action=action,
                opportunity_score=opportunity_score_from_row(row),
                model_score=_f(row, "ai_confidence", "model_score", default=None),
                expected_value=_f(opp, "expected_value", default=_f(row, "expected_value")),
                expected_return_pct=_f(opp, "expected_return_pct", default=_f(row, "expected_return_pct")),
                expected_risk_pct=_f(opp, "expected_loss_pct", "expected_risk_pct", default=None),
                risk_reward=_f(opp, "risk_reward", default=_f(row, "risk_reward")),
                confidence=_f(row, "ai_confidence", default=_f(scores, "ai_confidence")),
                regime=str(row.get("regime") or "") or None,
                mtf=mtf,
                liquidity_ok=float(scores.get("liquidity") or 50) >= 35,
                spread_ok=spread_ok,
                is_favorite=bool(row.get("is_favorite")),
            )
        )
    scored.sort(key=lambda x: (-x.opportunity_score, x.symbol))
    top = scored[: max(1, top_n)]
    # Competitive analysis annotations
    for i, opp in enumerate(top):
        opp.rank = i + 1
        if i == 0 and len(top) > 1:
            rival = top[1]
            opp.why_better = _compare(opp, rival, better=True)
            rival.why_worse = _compare(rival, opp, better=False)
        elif i > 0:
            best = top[0]
            opp.why_worse = _compare(opp, best, better=False)
            opp.why_better = _compare(opp, best, better=True)[:2]
    return top


def _compare(a: RankedOpportunity, b: RankedOpportunity, *, better: bool) -> list[str]:
    out: list[str] = []
    if (a.expected_value or -999) > (b.expected_value or -999):
        out.append("HIGHER_EXPECTED_VALUE" if better else "LOWER_EXPECTED_VALUE_VS_BEST")
    if (a.risk_reward or 0) > (b.risk_reward or 0):
        out.append("BETTER_RISK_REWARD" if better else "WEAKER_RISK_REWARD_VS_BEST")
    if a.spread_ok and not b.spread_ok:
        out.append("SPREAD_OK")
    if a.liquidity_ok and not b.liquidity_ok:
        out.append("LIQUIDITY_OK")
    if a.is_favorite and not b.is_favorite:
        out.append("FAVORITE_PRIORITY")
    if (a.opportunity_score or 0) > (b.opportunity_score or 0) and better:
        out.append("HIGHER_OPPORTUNITY_SCORE")
    return out[:6]


def competitive_summary(ranked: list[RankedOpportunity]) -> dict[str, Any]:
    if not ranked:
        return {"best": None, "second": None, "third": None, "note": "NO_CLEAR_EDGE"}
    return {
        "best": ranked[0].to_dict() if len(ranked) > 0 else None,
        "second": ranked[1].to_dict() if len(ranked) > 1 else None,
        "third": ranked[2].to_dict() if len(ranked) > 2 else None,
        "compared": [r.symbol for r in ranked[:5]],
        "note": "Opportunity score ≠ trading permission; RiskEngine is final",
    }
