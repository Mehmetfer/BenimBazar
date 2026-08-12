"""SI-1 … SI-10 acceptance scorecard — evidence only, no inflation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["PASS", "PARTIAL", "FAIL", "NOT VERIFIED"]


@dataclass
class Gate:
    id: str
    name: str
    status: Status
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SIScorecard:
    engineering_autonomy: float
    decision_autonomy: float
    self_improvement_level: float
    live_money_autonomy: str
    full_level8_claimed: bool
    gates: list[Gate]
    verdict: str
    roadmap: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engineering_autonomy": self.engineering_autonomy,
            "decision_autonomy": self.decision_autonomy,
            "self_improvement_level": self.self_improvement_level,
            "live_money_autonomy": self.live_money_autonomy,
            "full_level8_claimed": self.full_level8_claimed,
            "gates": [g.to_dict() for g in self.gates],
            "verdict": self.verdict,
            "roadmap": self.roadmap,
            "notes": self.notes,
        }


def _st(ok: bool, partial: bool = False) -> Status:
    if ok:
        return "PASS"
    if partial:
        return "PARTIAL"
    return "FAIL"


def score_self_improvement(
    *,
    engineering: float = 8.45,
    decision: float = 8.5,
    si1_audit: bool,
    si2_planning: bool,
    si3_implementation: bool,
    si4_testing: bool,
    si5_regression: bool,
    si6_recovery: bool,
    si7_learning: bool,
    si8_optimization: bool = False,
    si9_architecture: bool = False,
    si10_continuous: bool = False,
) -> SIScorecard:
    gates = [
        Gate("SI-1", "Self Audit", _st(si1_audit), ["audit_repository"]),
        Gate("SI-2", "Self Planning", _st(si2_planning), ["BacklogStore"]),
        Gate("SI-3", "Self Implementation", _st(si3_implementation), ["sandbox apply"]),
        Gate("SI-4", "Self Testing", _st(si4_testing), ["verify pytest"]),
        Gate("SI-5", "Self Regression", _st(si5_regression), ["baseline lock"]),
        Gate("SI-6", "Self Recovery", _st(si6_recovery), ["sandbox.rollback"]),
        Gate("SI-7", "Self Learning", _st(si7_learning), ["AttemptRecord + lessons"]),
        Gate("SI-8", "Self Optimization", _st(si8_optimization, partial=False), ["perf evidence required"]),
        Gate("SI-9", "Self Architecture", _st(si9_architecture), ["proposal+benchmark required"]),
        Gate("SI-10", "Continuous Improvement", _st(si10_continuous, partial=si1_audit and si2_planning), ["loop.next"]),
    ]
    passed = sum(1 for g in gates if g.status == "PASS")
    # Roadmap levels — do not jump to 9.6 without SI-8/9/10
    if passed >= 7 and si1_audit and si3_implementation and si4_testing and si5_regression and si6_recovery:
        level = 9.2  # Self Testing proven (+ recovery/learning path)
        if si8_optimization:
            level = 9.4
        if si8_optimization and si9_architecture:
            level = 9.6
        if si8_optimization and si9_architecture and si10_continuous:
            level = 9.8
        # Cap: without SI-8/9 cannot claim 9.6+
        if not si8_optimization:
            level = min(level, 9.2)
        verdict = f"{level} SELF-IMPROVEMENT PARTIAL/VERIFIED (see gates); LIVE-MONEY NOT VERIFIED"
    elif passed >= 4:
        level = 9.0
        verdict = "9.0 SELF-IMPROVEMENT FOUNDATION (audit/plan/impl/test path); higher gates open"
    else:
        level = min(8.7, engineering)
        verdict = "SELF-IMPROVEMENT NOT VERIFIED"

    # Never claim 10.0 here
    level = min(level, 9.2) if not (si8_optimization and si9_architecture and si10_continuous) else min(level, 9.8)
    if level >= 10.0:
        level = 9.8

    return SIScorecard(
        engineering_autonomy=engineering,
        decision_autonomy=decision,
        self_improvement_level=level,
        live_money_autonomy="NOT VERIFIED",
        full_level8_claimed=False,
        gates=gates,
        verdict=verdict,
        roadmap=[
            "8.45 engineering",
            "8.5 / 9.0 decision autonomy (paper)",
            "9.2 Self Testing (+ recovery/learning)",
            "9.4 Self Recovery soak / optimization evidence",
            "9.6 Self Improvement (architecture proposals proven)",
            "9.8 Continuous Verified Improvement",
            "10.0 Controlled Self-Evolving — separate live + long soak",
        ],
        notes=[
            "Scores from SI gate evidence only; not inflated.",
            "SI cannot loosen risk limits / kill switch / LIVE unlock.",
            "LIVE-MONEY AUTONOMY remains NOT VERIFIED.",
        ],
    )
