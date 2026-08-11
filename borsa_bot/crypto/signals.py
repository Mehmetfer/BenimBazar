"""Crypto signal decision — MODEL_SCORE + technical confirmation + risk."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config.models import CapitalMode, OpportunityMetrics, SignalAction
from config.settings import Settings, settings as default_settings
from crypto.analytics import CryptoTechnicalSnapshot
from crypto.risk_crypto import CryptoRiskResult
from crypto.trade_plan_crypto import CryptoTradePlanView
from profit.ev import compute_opportunity, decide_matrix, dynamic_size_multiplier


@dataclass
class CryptoSignalResult:
    symbol: str
    market_type: str = "CRYPTO"
    signal: str = SignalAction.NO_TRADE.value
    model_score: float = 0.0
    model_score_definition: str = ""
    # Explicit: do NOT present model_score as calibrated probability
    probability_label: str = "NOT_A_PROBABILITY"
    technical_ok: bool = False
    confirmation_count: int = 0
    confirmations: list[str] = field(default_factory=list)
    mtf: dict[str, str] = field(default_factory=dict)
    risk: dict[str, Any] | None = None
    trade_plan: dict[str, Any] | None = None
    opportunity: dict[str, Any] | None = None
    note: str = ""
    data_source_kind: str = "LIVE"
    provider: str = "paribu"
    paper_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_crypto_signal(
    tech: CryptoTechnicalSnapshot,
    *,
    plan: CryptoTradePlanView | None,
    risk: CryptoRiskResult | None,
    price: float,
    owned: bool = False,
    capital_mode: CapitalMode = CapitalMode.NORMAL,
    portfolio_dd_pct: float = 0.0,
    cfg: Settings | None = None,
) -> CryptoSignalResult:
    cfg = cfg or default_settings
    out = CryptoSignalResult(
        symbol=tech.symbol,
        model_score=tech.model_score,
        model_score_definition=tech.model_score_definition,
        confirmation_count=tech.confirmation_count,
        confirmations=list(tech.confirmations),
        mtf=dict(tech.mtf),
        technical_ok=tech.ok,
    )
    if not tech.ok or tech.scores is None or tech.indicators is None:
        out.signal = SignalAction.NO_TRADE.value
        out.note = tech.note or "NO_SIGNAL"
        return out

    if tech.mtf_conflict:
        out.signal = SignalAction.WAIT.value
        out.note = f"MTF_CONFLICT:{tech.mtf_note}"
        return out

    if plan is None:
        out.signal = SignalAction.NO_TRADE.value
        out.note = "NO_TRADE_PLAN"
        return out

    legacy = plan.to_legacy()
    opp = compute_opportunity(
        scores=tech.scores,
        plan=legacy,
        price=price,
        ind=tech.indicators,
        regime=tech.regime,
        conflict=tech.mtf_conflict,
        mtf_aligned=tech.mtf_aligned,
        portfolio_dd_pct=portfolio_dd_pct,
        cfg=cfg,
    )
    if opp is None:
        out.signal = SignalAction.NO_TRADE.value
        out.note = "NO_OPPORTUNITY"
        return out

    size_mult = dynamic_size_multiplier(opp, capital_mode=capital_mode, regime=tech.regime, cfg=cfg)
    opp.position_size_mult = size_mult

    action = decide_matrix(
        scores=tech.scores,
        opp=opp,
        owned=owned,
        sell_pressure=tech.scores.risk,
        conflict=tech.mtf_conflict,
        news_block=False,
        capital_mode=capital_mode,
        regime=tech.regime,
        cfg=cfg,
    )

    # Require technical confirmation for BUY-side
    if action in {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}:
        if tech.confirmation_count < 2:
            action = SignalAction.WAIT
            out.note = "INSUFFICIENT_TECHNICAL_CONFIRMATION"
        elif tech.model_score < cfg.watch_threshold:
            action = SignalAction.WAIT
            out.note = "MODEL_SCORE_BELOW_WATCH"

    # Risk gate — BUY without risk approval → WAIT / NO_TRADE
    if risk is not None:
        out.risk = risk.to_dict()
        if action in {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}:
            if not risk.allowed:
                action = SignalAction.WAIT if risk.verdict == "WAIT" else SignalAction.NO_TRADE
                out.note = f"RISK_BLOCK:{risk.reason}"
            else:
                # adopt risk-adjusted size
                plan.position_size = risk.quantity
                out.note = out.note or "ok"
        if action in {SignalAction.SELL, SignalAction.STRONG_SELL, SignalAction.SAT}:
            # exit side — risk must not block kill-switch only
            if risk.reason == "KILL_SWITCH":
                action = SignalAction.NO_TRADE
                out.note = "KILL_SWITCH"

    out.signal = action.value
    out.trade_plan = plan.to_dict()
    out.opportunity = {
        "expected_value": opp.expected_value,
        "risk_reward": opp.risk_reward,
        "heuristic_p_win": opp.p_win,  # labeled heuristic — not calibrated
        "heuristic_p_win_note": "Heuristic confluence estimate from profit.ev — NOT calibrated probability",
        "volatility_pct": opp.volatility_pct,
        "size_mult": size_mult,
        "model_score": tech.model_score,
    }
    if not out.note:
        out.note = "ok"
    return out
