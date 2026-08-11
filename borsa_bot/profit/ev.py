from __future__ import annotations

from config.models import CapitalMode, IndicatorSet, MarketRegime, OpportunityMetrics, ScoreBundle, TradePlan
from config.settings import Settings, settings as default_settings


def estimate_p_win(
    scores: ScoreBundle,
    *,
    regime: MarketRegime,
    conflict: bool,
    mtf_aligned: bool,
) -> float:
    """Heuristic success probability from confluence — not a calibrated forecast."""
    base = 0.35 + (scores.final / 100.0) * 0.40
    base += (scores.ai_confidence - 50) / 100.0 * 0.10
    if scores.volume >= 70:
        base += 0.04
    if scores.liquidity >= 70:
        base += 0.03
    if mtf_aligned:
        base += 0.05
    if conflict:
        base -= 0.12
    if regime == MarketRegime.STRONG_BEAR:
        base -= 0.15
    elif regime == MarketRegime.BEAR:
        base -= 0.08
    elif regime == MarketRegime.STRONG_BULL:
        base += 0.05
    return max(0.05, min(0.90, base))


def compute_opportunity(
    *,
    scores: ScoreBundle,
    plan: TradePlan | None,
    price: float,
    ind: IndicatorSet,
    regime: MarketRegime,
    conflict: bool,
    mtf_aligned: bool,
    portfolio_dd_pct: float,
    cfg: Settings | None = None,
) -> OpportunityMetrics | None:
    cfg = cfg or default_settings
    if plan is None or price <= 0:
        return None
    risk_pct = (plan.entry - plan.stop) / plan.entry * 100
    reward_pct = (plan.target1 - plan.entry) / plan.entry * 100
    if risk_pct <= 0:
        return None
    p_win = estimate_p_win(scores, regime=regime, conflict=conflict, mtf_aligned=mtf_aligned)
    p_loss = 1.0 - p_win
    # EV in % of entry notional (pre-size)
    ev = p_win * reward_pct - p_loss * risk_pct
    atr_pct = ind.atr14 / price * 100 if price else 0.0
    # Drawdown impact proxy: risk fraction of portfolio if full R loss
    dd_impact = risk_pct * (cfg.max_position_risk_pct / max(risk_pct, 0.01))
    dd_impact = min(dd_impact, cfg.max_position_risk_pct)
    # Soft penalty if already in drawdown
    if portfolio_dd_pct > cfg.defensive_dd_pct:
        dd_impact *= 1.25
    return OpportunityMetrics(
        p_win=round(p_win, 3),
        expected_return_pct=round(reward_pct, 3),
        expected_loss_pct=round(risk_pct, 3),
        risk_reward=round(plan.risk_reward, 2),
        expected_value=round(ev, 4),
        volatility_pct=round(atr_pct, 3),
        drawdown_impact=round(dd_impact, 3),
        position_size_mult=1.0,
        confidence=round(scores.ai_confidence, 1),
    )


def dynamic_size_multiplier(
    opp: OpportunityMetrics,
    *,
    capital_mode: CapitalMode,
    regime: MarketRegime,
    cfg: Settings | None = None,
) -> float:
    """Scale risk budget — not a fixed TL amount."""
    cfg = cfg or default_settings
    mult = 1.0
    # Confidence / EV quality
    if opp.confidence >= 80 and opp.expected_value > 1.0 and opp.volatility_pct < 3.0:
        mult = 1.0  # full size for strong setup
    elif opp.confidence >= 70 and opp.expected_value > 0.3:
        mult = 0.75
    else:
        mult = 0.5  # medium / uncertain → shrink

    if opp.volatility_pct >= 4.0:
        mult *= 0.55
    elif opp.volatility_pct >= 3.0:
        mult *= 0.75

    if capital_mode == CapitalMode.DEFENSIVE:
        mult *= 0.5
    elif capital_mode == CapitalMode.HIGH_RISK:
        mult *= 0.35
    elif capital_mode == CapitalMode.CAPITAL_PROTECTION:
        mult *= 0.0
    elif capital_mode == CapitalMode.KILL_SWITCH:
        mult *= 0.0

    if regime == MarketRegime.BEAR:
        mult *= 0.6
    elif regime == MarketRegime.STRONG_BEAR:
        mult *= 0.0

    return max(0.0, min(1.0, round(mult, 3)))


def decide_matrix(
    *,
    scores: ScoreBundle,
    opp: OpportunityMetrics | None,
    owned: bool,
    sell_pressure: float,
    conflict: bool,
    news_block: bool,
    capital_mode: CapitalMode,
    regime: MarketRegime,
    cfg: Settings | None = None,
):
    """Final decision matrix — NO_TRADE / WAIT are first-class."""
    from config.models import SignalAction

    cfg = cfg or default_settings
    if capital_mode == CapitalMode.KILL_SWITCH:
        return SignalAction.NO_TRADE
    if news_block or conflict:
        return SignalAction.WAIT if not owned else SignalAction.WATCH
    if opp is None:
        return SignalAction.NO_TRADE
    if opp.expected_value <= cfg.min_expected_value:
        return SignalAction.NO_TRADE
    if capital_mode == CapitalMode.CAPITAL_PROTECTION:
        return SignalAction.NO_TRADE
    if owned and sell_pressure >= cfg.sell_score_threshold + 10:
        return SignalAction.STRONG_SELL
    if owned and sell_pressure >= cfg.sell_score_threshold:
        return SignalAction.SELL
    if owned:
        return SignalAction.WATCH

    # Long side
    if regime == MarketRegime.STRONG_BEAR:
        return SignalAction.NO_TRADE
    if capital_mode == CapitalMode.HIGH_RISK and not (
        scores.final >= cfg.strong_buy_threshold and opp.expected_value > 1.0 and opp.p_win >= 0.6
    ):
        return SignalAction.NO_TRADE

    if (
        scores.final >= cfg.strong_buy_threshold
        and opp.p_win >= 0.62
        and opp.expected_value > 0.8
        and scores.risk <= 35
        and scores.liquidity >= 60
    ):
        return SignalAction.STRONG_BUY
    if (
        scores.final >= cfg.buy_score_threshold
        and opp.expected_value > 0.0
        and opp.risk_reward >= cfg.min_risk_reward
        and scores.market >= 45
    ):
        return SignalAction.BUY
    if scores.final >= cfg.watch_threshold:
        return SignalAction.WATCH
    if scores.final < 40:
        return SignalAction.NO_TRADE
    return SignalAction.WAIT
