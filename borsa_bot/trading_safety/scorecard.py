"""Trading autonomy scorecard — separate from engineering autonomy 8.45."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["PASS", "PARTIAL", "FAIL", "NOT VERIFIED"]


@dataclass
class Criterion:
    name: str
    weight: float
    status: Status
    score: float  # 0-10 contribution before weight
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradingAutonomyScorecard:
    engineering_autonomy_score: float
    trading_safety_score: float
    live_money_readiness: str
    full_level8_claimed: bool
    verdict: str
    criteria: list[Criterion]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engineering_autonomy_score": self.engineering_autonomy_score,
            "trading_safety_score": self.trading_safety_score,
            "live_money_readiness": self.live_money_readiness,
            "full_level8_claimed": self.full_level8_claimed,
            "verdict": self.verdict,
            "criteria": [c.to_dict() for c in self.criteria],
            "notes": self.notes,
        }


def _st(ok: bool, partial: bool = False) -> tuple[Status, float]:
    if ok:
        return "PASS", 10.0
    if partial:
        return "PARTIAL", 6.0
    return "FAIL", 0.0


def score_trading_autonomy(
    *,
    engineering_score: float = 8.45,
    safety_gates_ok: bool,
    fail_closed_ok: bool,
    idempotency_ok: bool,
    unknown_order_ok: bool,
    reconciliation_ok: bool,
    restart_recovery_ok: bool,
    risk_controls_ok: bool,
    kill_circuit_ok: bool,
    observability_audit_ok: bool,
    adversarial_e2e_ok: bool,
    live_broker_locked: bool,
    critical_findings: int = 0,
    all_mandatory_pass: bool = False,
) -> TradingAutonomyScorecard:
    criteria = [
        Criterion("Safety gates", 0.15, *_st(safety_gates_ok), evidence=["order_gate + pipeline"]),
        Criterion("Fail-closed behavior", 0.10, *_st(fail_closed_ok), evidence=["unknown!=safe tests"]),
        Criterion("Order idempotency", 0.10, *_st(idempotency_ok), evidence=["duplicate key blocked"]),
        Criterion("Unknown-order recovery", 0.10, *_st(unknown_order_ok), evidence=["UNKNOWN not assumed failed"]),
        Criterion("Reconciliation", 0.10, *_st(reconciliation_ok), evidence=["qty/cash mismatch blocks"]),
        Criterion("Restart recovery", 0.10, *_st(restart_recovery_ok), evidence=["recover_after_restart"]),
        Criterion("Risk controls", 0.10, *_st(risk_controls_ok), evidence=["limits + micro caps"]),
        Criterion("Kill/circuit breakers", 0.10, *_st(kill_circuit_ok), evidence=["kill_switch + circuit_breaker"]),
        Criterion("Observability/audit", 0.05, *_st(observability_audit_ok), evidence=["audit append-only + metrics"]),
        Criterion("Adversarial E2E tests", 0.10, *_st(adversarial_e2e_ok), evidence=["test_trading_safety_*"]),
    ]
    score = round(sum(c.score * c.weight for c in criteria), 2)

    live_ready = "NOT VERIFIED"
    # Never claim live-money verified in this protocol
    if not live_broker_locked:
        live_ready = "NOT VERIFIED"
        score = min(score, 3.0)

    full_l8 = False  # research/paper ≠ live-money; never flip here

    if critical_findings > 0 or not all_mandatory_pass:
        verdict = "9.0 NOT VERIFIED"
    elif score >= 9.0 and live_ready == "NOT VERIFIED":
        # Can verify trading *safety* autonomy without live money
        verdict = "TRADING SAFETY ≥9.0 VERIFIED; LIVE MONEY READINESS NOT VERIFIED"
    elif score >= 9.0:
        verdict = "TRADING SAFETY ≥9.0 VERIFIED"
    else:
        verdict = "9.0 NOT VERIFIED"

    notes = [
        f"Engineering autonomy unchanged baseline claim: {engineering_score}",
        "full_level8_claimed remains False unless separate live-money acceptance",
        "MICRO_LIVE caps exist but do not enable real broker automatically",
    ]
    return TradingAutonomyScorecard(
        engineering_autonomy_score=engineering_score,
        trading_safety_score=score,
        live_money_readiness=live_ready,
        full_level8_claimed=full_l8,
        verdict=verdict,
        criteria=criteria,
        notes=notes,
    )
