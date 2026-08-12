"""Decision autonomy scorecard — honest evidence-based scoring toward 8.5+."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["PASS", "PARTIAL", "FAIL", "NOT VERIFIED"]


@dataclass
class Criterion:
    name: str
    weight: float
    status: Status
    score: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionAutonomyScorecard:
    engineering_autonomy_score: float
    decision_autonomy_score: float
    trading_safety_score: float
    live_money_autonomy: str
    full_level8_claimed: bool
    verdict: str
    criteria: list[Criterion]
    roadmap: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engineering_autonomy_score": self.engineering_autonomy_score,
            "decision_autonomy_score": self.decision_autonomy_score,
            "trading_safety_score": self.trading_safety_score,
            "live_money_autonomy": self.live_money_autonomy,
            "full_level8_claimed": self.full_level8_claimed,
            "verdict": self.verdict,
            "criteria": [c.to_dict() for c in self.criteria],
            "roadmap": self.roadmap,
            "notes": self.notes,
        }


def _st(ok: bool, partial: bool = False) -> tuple[Status, float]:
    if ok:
        return "PASS", 10.0
    if partial:
        return "PARTIAL", 6.0
    return "FAIL", 0.0


def score_decision_autonomy(
    *,
    engineering_score: float = 8.45,
    trading_safety_score: float = 10.0,
    decision_states_ok: bool,
    chain_complete_ok: bool,
    no_trade_ok: bool,
    position_sizing_hard_cap_ok: bool,
    immutable_limits_ok: bool,
    adaptive_no_bypass_ok: bool,
    self_correction_ok: bool,
    decision_validator_ok: bool,
    confidence_gate_ok: bool,
    humanless_e2e_ok: bool,
    failure_acceptance_ok: bool,
    live_money_verified: bool = False,
) -> DecisionAutonomyScorecard:
    criteria = [
        Criterion("Decision states (BUY..NO_TRADE)", 0.10, *_st(decision_states_ok), evidence=["states.py + tests"]),
        Criterion("Decision chain completeness", 0.12, *_st(chain_complete_ok), evidence=["chain.py stages"]),
        Criterion("NO_TRADE as first-class", 0.10, *_st(no_trade_ok), evidence=["abstain conditions"]),
        Criterion("Position sizing hard cap", 0.10, *_st(position_sizing_hard_cap_ok), evidence=["sizing <= hard_max"]),
        Criterion("Immutable safety limits", 0.10, *_st(immutable_limits_ok), evidence=["frozen limits"]),
        Criterion("Adaptive no safety bypass", 0.08, *_st(adaptive_no_bypass_ok), evidence=["learning rejects frozen"]),
        Criterion("Self-correction protocol", 0.08, *_st(self_correction_ok), evidence=["DETECT→VERIFY"]),
        Criterion("Decision+risk validators", 0.10, *_st(decision_validator_ok), evidence=["validator.py"]),
        Criterion("Confidence gate (not authority)", 0.07, *_st(confidence_gate_ok), evidence=["confidence.py"]),
        Criterion("Humanless E2E acceptance", 0.10, *_st(humanless_e2e_ok), evidence=["test_ade_humanless_e2e"]),
        Criterion("Failure acceptance matrix", 0.05, *_st(failure_acceptance_ok), evidence=["KNOWN SAFE/UNSAFE"]),
    ]
    raw = round(sum(c.score * c.weight for c in criteria), 2)

    core_ok = all(
        [
            decision_states_ok,
            chain_complete_ok,
            no_trade_ok,
            position_sizing_hard_cap_ok,
            immutable_limits_ok,
            adaptive_no_bypass_ok,
            decision_validator_ok,
            humanless_e2e_ok,
            self_correction_ok,
            confidence_gate_ok,
            failure_acceptance_ok,
        ]
    )

    # Autonomy *level* (roadmap), not raw criterion average — do not inflate past proven milestone.
    # 8.5 = ADE humanless paper/shadow proven; 8.7+ requires deeper execution/recovery soak.
    if not humanless_e2e_ok or not decision_states_ok or not chain_complete_ok:
        level = min(7.5, round(8.0 * (raw / 10.0), 2))
        verdict = "DECISION AUTONOMY NOT VERIFIED"
    elif not core_ok:
        level = min(8.2, round(8.2 * (raw / 10.0), 2))
        verdict = "DECISION AUTONOMY PARTIAL — below 8.5 claim threshold"
    else:
        # Proven ADE acceptance → claim 8.5 only (next milestones need new evidence)
        level = 8.5
        verdict = (
            "8.5 AUTONOMOUS DECISION ENGINE VERIFIED (paper/shadow); "
            "LIVE-MONEY AUTONOMY NOT VERIFIED"
        )

    live = "NOT VERIFIED"
    full_l8 = False

    roadmap = [
        "8.45 engineering (coding/validation) — prior",
        "8.5 Autonomous Decision Engine — this scorecard",
        "8.7 Autonomous Execution + Recovery — longer recovery matrix",
        "8.9 Long-duration Humanless Validation — multi-session soak",
        "9.0+ Production Trading Autonomy — requires LIVE-MONEY acceptance (separate)",
    ]

    return DecisionAutonomyScorecard(
        engineering_autonomy_score=engineering_score,
        decision_autonomy_score=level,
        trading_safety_score=trading_safety_score,
        live_money_autonomy=live,
        full_level8_claimed=full_l8,
        verdict=verdict,
        criteria=criteria,
        roadmap=roadmap,
        notes=[
            f"Criterion raw weighted average={raw}/10 (quality of ADE suite); claimed autonomy level={level}.",
            "Scores from evidence only; not inflated past the proven roadmap milestone.",
            "Learning cannot mutate risk limits / kill switch / fail-closed / auth.",
            "LIVE-MONEY AUTONOMY = VERIFIED is forbidden until dedicated live acceptance.",
        ],
    )
