"""Software Engineering Autonomy scorecard — computed from benchmarks only."""

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
class SEAutonomyScorecard:
    previous_engineering: float
    previous_si: float
    software_engineering_autonomy: float
    live_money_autonomy: str
    full_level8_claimed: bool
    verdict: str
    criteria: list[Criterion]
    benchmark_passed: int
    benchmark_total: int
    roadmap: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_engineering": self.previous_engineering,
            "previous_si": self.previous_si,
            "software_engineering_autonomy": self.software_engineering_autonomy,
            "live_money_autonomy": self.live_money_autonomy,
            "full_level8_claimed": self.full_level8_claimed,
            "verdict": self.verdict,
            "criteria": [c.to_dict() for c in self.criteria],
            "benchmark_passed": self.benchmark_passed,
            "benchmark_total": self.benchmark_total,
            "roadmap": self.roadmap,
            "notes": self.notes,
        }


def _st(ok: bool, partial: bool = False) -> tuple[Status, float]:
    if ok:
        return "PASS", 10.0
    if partial:
        return "PARTIAL", 6.0
    return "FAIL", 0.0


def score_software_engineering_autonomy(
    *,
    previous_engineering: float = 8.45,
    previous_si: float = 9.2,
    bench: dict[str, bool],
    benchmark_passed: int,
    benchmark_total: int,
) -> SEAutonomyScorecard:
    """Weights from the AUTONOMY 10 spec."""
    criteria = [
        Criterion("Repository understanding", 0.10, *_st(bench.get("repository_understanding", False)), evidence=["discover_repository"]),
        Criterion("Task decomposition", 0.10, *_st(bench.get("task_decomposition", False)), evidence=["decompose_goal"]),
        Criterion("Autonomous implementation", 0.15, *_st(bench.get("bug_fix_tdd", False) or bench.get("missing_test", False)), evidence=["run_goal implement"]),
        Criterion("Testing", 0.10, *_st(bench.get("missing_test", False)), evidence=["TDD / missing tests"]),
        Criterion("Debugging/recovery", 0.15, *_st(bench.get("debugging_recovery", False)), evidence=["repair_loop"]),
        Criterion("Regression prevention", 0.10, *_st(bench.get("refuse_assertion_weakening", False)), evidence=["review blockers"]),
        Criterion("Self-review", 0.05, *_st(bench.get("quality_gate", False)), evidence=["quality + review"]),
        Criterion("Tool orchestration", 0.05, *_st(bench.get("autonomous_file_discovery", False)), evidence=["find_files + pytest"]),
        Criterion("Memory/lessons", 0.05, *_st(bench.get("repository_understanding", False)), evidence=["codebase_memory.json"]),
        Criterion("Long-running execution", 0.10, *_st(bench.get("long_run_stages", False)), evidence=["ASE stages"]),
        Criterion("Self-improvement", 0.05, *_st(previous_si >= 9.0, partial=previous_si >= 8.5), evidence=["self_improvement package"]),
    ]
    raw = round(sum(c.score * c.weight for c in criteria), 2)

    # Map raw 0-10 weighted to roadmap level — do not claim 10.0
    if benchmark_passed < max(1, benchmark_total // 2):
        level = min(8.7, raw)
        verdict = "SOFTWARE ENGINEERING AUTONOMY NOT VERIFIED"
        status_word = "NOT VERIFIED"
    elif benchmark_passed == benchmark_total and raw >= 9.0:
        # Full bench pass → claim 9.4 Autonomous Testing / debugging band (not 10)
        level = 9.4
        verdict = "9.4 SOFTWARE ENGINEERING AUTONOMY PARTIALLY VERIFIED (benchmark suite); LIVE-MONEY NOT VERIFIED"
        status_word = "PARTIALLY VERIFIED"
        # Cap honesty: without multi-hour soak / parallel agents, not 9.6+
    elif benchmark_passed >= int(0.8 * benchmark_total):
        level = 9.2
        verdict = "9.2 SOFTWARE ENGINEERING AUTONOMY PARTIALLY VERIFIED; LIVE-MONEY NOT VERIFIED"
        status_word = "PARTIALLY VERIFIED"
    else:
        level = 9.0
        verdict = "9.0 AUTONOMOUS CODING FOUNDATION; higher levels need more benches"
        status_word = "PARTIALLY VERIFIED"

    # Never 10.0 from this suite alone
    level = min(level, 9.4)

    return SEAutonomyScorecard(
        previous_engineering=previous_engineering,
        previous_si=previous_si,
        software_engineering_autonomy=level,
        live_money_autonomy="NOT VERIFIED",
        full_level8_claimed=False,
        verdict=f"{verdict} [{status_word}]",
        criteria=criteria,
        benchmark_passed=benchmark_passed,
        benchmark_total=benchmark_total,
        roadmap=[
            "8.45 engineering",
            "9.0 Autonomous Coding",
            "9.2 Autonomous Debugging",
            "9.4 Autonomous Testing",
            "9.6 Long-running Agent",
            "9.8 Self-improving Agent",
            "10.0 Verified Autonomous Software Engineer",
        ],
        notes=[
            f"Criterion raw weighted average={raw}/10; claimed level={level} from benchmarks only.",
            "Not a claim of ChatGPT/Cursor model parity — workflow autonomy inside this repo.",
            "Forbidden: test deletion, assertion weakening, safety bypass, LIVE unlock.",
        ],
    )
