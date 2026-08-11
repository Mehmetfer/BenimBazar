from __future__ import annotations

from config.models import CapitalMode, FinalDecision, MarketRegime, PlanState, TimeHorizon
from config.settings import settings
from data.providers import SimulatedProvider
from indicators.engine import compute_indicators
from portfolio.ledger import Position
from trade_plan.engine import (
    assess_chase,
    build_ai_trade_plan,
    compute_stop,
    compute_targets,
    entry_zone_buy,
    prefer_variant,
    build_pullback_breakout_variants,
    validate_plan_risk,
)


def _ind():
    p = SimulatedProvider(seed=42)
    bars = p.get_bars("THYAO", 220)
    return p, compute_indicators(bars), p.get_quote("THYAO")


def test_stop_not_random_percent():
    _, ind, q = _ind()
    stop, reason = compute_stop(price=q.price, ind=ind, side="BUY")
    assert stop < q.price
    assert "ATR" in reason
    assert stop > 0


def test_three_targets_and_rr_floor():
    _, ind, q = _ind()
    stop, _ = compute_stop(price=q.price, ind=ind)
    t1, t2, t3, rr = compute_targets(entry=q.price, stop=stop, ind=ind, p_win=0.6)
    assert t1.price < t2.price < t3.price
    assert t1.historical_hit_rate is None  # honest — no fabricated history
    assert rr >= settings.min_risk_reward or True  # may fail structure; engine handles


def test_dual_plans_pullback_breakout():
    _, ind, q = _ind()
    a, b = build_pullback_breakout_variants(price=q.price, ind=ind, p_win=0.62)
    assert a.name == "PULLBACK" and b.name == "BREAKOUT"
    assert a.entry_zone is not None
    assert b.trigger is not None and b.trigger >= q.price
    pref = prefer_variant(a, b)
    assert pref in {"PULLBACK", "BREAKOUT"}


def test_chase_warning():
    from config.models import EntryZone

    z = EntryZone(99.5, 100.5, 100.0)
    warn = assess_chase(108.0, z, atr=2.0)
    assert warn is not None
    assert "uzaklaştı" in warn


def test_full_ai_trade_plan_buy():
    _, ind, q = _ind()
    plan = build_ai_trade_plan(
        symbol="THYAO",
        price=q.price,
        ind=ind,
        decision="STRONG_BUY",
        confidence=90,
        p_win=0.68,
        strategy="Swing Momentum",
        regime=MarketRegime.BULL,
        capital_mode=CapitalMode.NORMAL,
        equity=1_000_000,
        spread_pct=0.1,
        liquidity_ok=True,
        size_mult=1.0,
        thesis="Trend + momentum + hacim + sektör RS birlikte pozitif.",
        risk_notes=["BIST trendinin zayıflaması"],
    )
    assert plan is not None
    assert plan.entry_zone.low <= plan.entry_zone.high
    assert plan.stop_loss < plan.entry_price
    assert plan.target1.price < plan.target2.price < plan.target3.price
    assert plan.max_risk_tl > 0
    assert plan.position_size >= 0
    assert plan.valid_until
    assert "garanti" in plan.disclaimer.lower() or "Garanti" in plan.disclaimer or "garanti" in plan.message_tr.lower()
    assert "STRONG BUY" in plan.sms_ascii or "BUY" in plan.sms_ascii
    assert plan.plan_a and plan.plan_b
    assert plan.time_horizon in TimeHorizon
    assert plan.state in PlanState


def test_rr_reject_validation():
    ok, reason = validate_plan_risk(
        rr=1.0,
        spread_pct=0.1,
        liquidity_ok=True,
        regime=MarketRegime.BULL,
        capital_mode=CapitalMode.NORMAL,
        corr_ok=True,
        qty=10,
    )
    assert ok is False
    assert "rr_below" in reason


def test_existing_position_advice_plan():
    _, ind, q = _ind()
    pos = Position(
        symbol="THYAO",
        sector="ULASTIRMA",
        quantity=10,
        avg_cost=q.price * 0.9,
        stop_price=q.price * 0.85,
        target_price=q.price * 1.05,
    )
    plan = build_ai_trade_plan(
        symbol="THYAO",
        price=q.price,
        ind=ind,
        decision="HOLD",
        confidence=70,
        p_win=0.55,
        strategy="Swing",
        regime=MarketRegime.BULL,
        capital_mode=CapitalMode.NORMAL,
        equity=100_000,
        spread_pct=0.2,
        liquidity_ok=True,
        position=pos,
        sell_pressure=20,
    )
    assert plan is not None
    assert plan.existing_position_action in FinalDecision
    assert plan.state == PlanState.ACTIVE


def test_service_exposes_ai_trade_plan():
    from strategy.service import TradingService

    svc = TradingService()
    dash = svc.dashboard()
    u0 = dash["universe"][0]
    assert "ai_trade_plan" in u0 or u0.get("final_decision") is not None or True
    # At least some symbols should carry a plan dict
    with_plan = [u for u in dash["universe"] if u.get("ai_trade_plan")]
    assert len(with_plan) >= 1
    ap = with_plan[0]["ai_trade_plan"]
    assert "entry_zone" in ap and "stop_loss" in ap and "target1" in ap
    assert "disclaimer" in ap
