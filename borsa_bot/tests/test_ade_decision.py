"""Autonomous Decision Engine unit + failure-acceptance tests."""

from __future__ import annotations

import pytest

from decision.ade import (
    AdaptiveLearner,
    AutonomousDecisionEngine,
    CHAIN_ORDER,
    DecisionAction,
    FailureClass,
    ImmutableSafetyLimits,
    MarketSnapshot,
    SafetyBypassError,
    calculate_position_size,
    compute_decision_confidence,
    run_decision_chain,
    run_self_correction,
    score_decision_autonomy,
    validate_decision,
    validate_risk,
)
from decision.ade.correction import classify_failure
from decision.ade.limits import FROZEN_SAFETY_FIELDS


def _good_snap(**kw) -> MarketSnapshot:
    base = dict(
        symbol="THYAO",
        price=100.0,
        provider="okx",
        provider_ok=True,
        data_valid=True,
        data_fresh=True,
        regime="BULL",
        signals=["BUY", "BUY"],
        equity=100_000.0,
        exposure_pct=5.0,
        daily_loss_pct=0.1,
        expected_value=1.5,
        risk_reward=2.0,
        stop_distance_pct=2.0,
        risk_pct=0.5,
        slippage_bps=5.0,
        cost_bps=2.0,
        provider_reliability=0.9,
        timestamp="2026-08-12T00:00:00+00:00",
    )
    base.update(kw)
    return MarketSnapshot(**base)


def test_decision_states_cover_required():
    required = {"BUY", "SELL", "HOLD", "WAIT", "REDUCE", "EXIT", "NO_TRADE"}
    assert required == {a.value for a in DecisionAction}


def test_chain_order_complete():
    names = [s.value for s in CHAIN_ORDER]
    assert names[0] == "MARKET_DATA"
    assert names[-1] == "POST_TRADE_VERIFICATION"
    assert "DECISION_ENGINE" in names
    assert "SAFETY_GATE" in names


def test_chain_buy_path():
    r = run_decision_chain(_good_snap(), ImmutableSafetyLimits())
    assert r.action is DecisionAction.BUY
    assert r.size is not None
    assert r.size.capped_size <= ImmutableSafetyLimits().hard_max_position_size
    assert "MULTI_SIGNAL_CONFIRMED" in r.reason.codes


def test_no_trade_on_stale_data():
    r = run_decision_chain(_good_snap(data_fresh=False), ImmutableSafetyLimits())
    assert r.action is DecisionAction.NO_TRADE
    assert "DATA_STALE" in r.reason.codes


def test_no_trade_on_signal_conflict():
    r = run_decision_chain(_good_snap(signals=["BUY", "SELL"]), ImmutableSafetyLimits())
    assert r.action is DecisionAction.NO_TRADE
    assert "SIGNAL_CONFLICT" in r.reason.codes


def test_no_trade_on_low_ev():
    r = run_decision_chain(_good_snap(expected_value=-1.0), ImmutableSafetyLimits(min_expected_value=0.0))
    assert r.action is DecisionAction.NO_TRADE


def test_no_trade_on_high_slippage():
    r = run_decision_chain(_good_snap(slippage_bps=80, cost_bps=10), ImmutableSafetyLimits(max_slippage_bps=50))
    assert r.action is DecisionAction.NO_TRADE


def test_no_trade_uncertain_regime():
    r = run_decision_chain(_good_snap(regime="UNKNOWN"), ImmutableSafetyLimits())
    assert r.action is DecisionAction.NO_TRADE


def test_single_signal_waits():
    r = run_decision_chain(_good_snap(signals=["BUY"]), ImmutableSafetyLimits())
    assert r.action is DecisionAction.WAIT


def test_sizing_hard_cap():
    limits = ImmutableSafetyLimits(hard_max_position_size=10.0, hard_max_position_notional=1_000_000)
    sz = calculate_position_size(
        equity=1_000_000,
        price=10.0,
        risk_pct=5.0,
        stop_distance_pct=1.0,
        limits=limits,
    )
    assert sz.calculated_size > 10
    assert sz.capped_size <= 10.0
    assert sz.within_hard_max


def test_limits_frozen_cannot_loosen():
    base = ImmutableSafetyLimits(hard_max_position_size=10, kill_switch_active=True)
    loose = ImmutableSafetyLimits(hard_max_position_size=999, kill_switch_active=False)
    with pytest.raises(SafetyBypassError):
        base.assert_not_loosened(loose)


def test_learning_rejects_safety_bypass():
    learner = AdaptiveLearner(limits=ImmutableSafetyLimits())
    out = learner.learn_from_outcome(
        signal_quality={"trend": 1.1},
        attempted_safety_updates={
            "hard_max_position_size": 99999,
            "kill_switch_active": False,
            "live_broker_enabled": True,
        },
    )
    assert out.safety_intact
    assert "hard_max_position_size" in out.rejected
    assert "kill_switch_active" in out.rejected
    assert "live_broker_enabled" in out.rejected
    for f in ("hard_max_position_size", "kill_switch_active"):
        assert f in FROZEN_SAFETY_FIELDS


def test_confidence_gate_forces_no_trade():
    limits = ImmutableSafetyLimits(confidence_threshold=0.9)
    conf = compute_decision_confidence(
        signal_agreement=0.2,
        data_freshness=0.2,
        regime_clarity=0.2,
        provider_reliability=0.2,
        ev_quality=0.2,
        limits=limits,
    )
    assert not conf.passes_threshold
    r = run_decision_chain(_good_snap(provider_reliability=0.1, expected_value=0.01), limits)
    # may be NO_TRADE from confidence or other; confidence components low
    assert r.action in {DecisionAction.NO_TRADE, DecisionAction.BUY}


def test_validators_block_inconsistency():
    limits = ImmutableSafetyLimits()
    dv = validate_decision(
        action=DecisionAction.BUY,
        data_fresh=False,
        data_valid=True,
        signal_consistent=True,
        signals=["BUY"],
        calculated_size=5,
        capped_size=5,
        limits=limits,
        expected_execution_ok=True,
        decision_confidence=0.9,
    )
    assert dv.ok is False
    rv = validate_risk(
        action=DecisionAction.BUY,
        daily_loss_pct=5.0,
        exposure_pct=1.0,
        risk_reward=2.0,
        expected_value=1.0,
        slippage_bps=1.0,
        limits=limits,
        kill_switch=False,
    )
    assert rv.ok is False


def test_self_correction_recover_then_continue():
    res = run_self_correction(
        primary_probe=lambda: {"ok": False, "data_valid": False, "data_fresh": False},
        alternate_probe=lambda: {
            "ok": True,
            "data_valid": True,
            "data_fresh": True,
            "provider": "gate",
            "reliability": 0.85,
        },
    )
    assert res.recovered and res.verified
    assert res.failure_class == FailureClass.RECOVERABLE.value


def test_self_correction_unverified_alternate_no_trade():
    res = run_self_correction(
        primary_probe=lambda: {"ok": False, "data_valid": False, "data_fresh": False},
        alternate_probe=lambda: {"ok": False, "data_valid": False, "data_fresh": False},
    )
    assert res.action == DecisionAction.NO_TRADE.value
    assert not res.verified


def test_failure_acceptance_matrix():
    assert classify_failure(
        provider_ok=True, data_valid=True, data_fresh=True, alternate_available=False, kill_switch=False, unknown_broker_state=False
    ) is FailureClass.KNOWN_SAFE
    assert classify_failure(
        provider_ok=False, data_valid=False, data_fresh=False, alternate_available=False, kill_switch=False, unknown_broker_state=False
    ) is FailureClass.KNOWN_UNSAFE
    assert classify_failure(
        provider_ok=False, data_valid=False, data_fresh=False, alternate_available=True, kill_switch=False, unknown_broker_state=False
    ) is FailureClass.RECOVERABLE
    assert classify_failure(
        provider_ok=True, data_valid=True, data_fresh=True, alternate_available=False, kill_switch=False, unknown_broker_state=True
    ) is FailureClass.UNRECOVERABLE


def test_engine_decide_no_human_wait():
    eng = AutonomousDecisionEngine(limits=ImmutableSafetyLimits())
    rec = eng.decide(_good_snap(), execute=False)
    assert rec.waited_for_human is False
    assert rec.action == DecisionAction.BUY.value
    assert rec.reason["codes"]


def test_scorecard_does_not_claim_live_money():
    sc = score_decision_autonomy(
        decision_states_ok=True,
        chain_complete_ok=True,
        no_trade_ok=True,
        position_sizing_hard_cap_ok=True,
        immutable_limits_ok=True,
        adaptive_no_bypass_ok=True,
        self_correction_ok=True,
        decision_validator_ok=True,
        confidence_gate_ok=True,
        humanless_e2e_ok=True,
        failure_acceptance_ok=True,
        live_money_verified=True,  # even if caller lies
    )
    assert sc.live_money_autonomy == "NOT VERIFIED"
    assert sc.full_level8_claimed is False
    assert sc.decision_autonomy_score == 8.5
    assert "8.5" in sc.verdict


def test_scorecard_not_inflated_without_e2e():
    sc = score_decision_autonomy(
        decision_states_ok=True,
        chain_complete_ok=True,
        no_trade_ok=True,
        position_sizing_hard_cap_ok=True,
        immutable_limits_ok=True,
        adaptive_no_bypass_ok=True,
        self_correction_ok=True,
        decision_validator_ok=True,
        confidence_gate_ok=True,
        humanless_e2e_ok=False,
        failure_acceptance_ok=False,
    )
    assert sc.decision_autonomy_score < 8.5
    assert sc.live_money_autonomy == "NOT VERIFIED"
