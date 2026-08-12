"""FAZ 8 / Verify-8 — Evidence-based weighted scorecard. No 8+ without mandatory proofs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from autonomy.levels import LevelResult, LevelStatus


@dataclass
class CriterionScore:
    id: int
    name: str
    score: float  # 0–10
    weight: float  # fraction summing to 1.0
    evidence: list[str] = field(default_factory=list)
    test_ids: list[str] = field(default_factory=list)
    limit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomyScorecard:
    overall: float
    criteria: list[CriterionScore]
    level_results: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = ""
    starting: float = 5.6
    notes: list[str] = field(default_factory=list)
    mandatory: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "starting": self.starting,
            "overall": self.overall,
            "verdict": self.verdict,
            "criteria": [c.to_dict() for c in self.criteria],
            "level_results": self.level_results,
            "notes": self.notes,
            "mandatory": self.mandatory,
        }


def score_autonomy(
    *,
    level_results: list[LevelResult],
    gates_ok: bool,
    gate_map: dict[str, bool] | None = None,
    lesson_count: int,
    self_review_ok: bool,
    baseline_pass: int,
    baseline_fail: int,
    live_locked: bool,
    domain_invariants_ok: bool = False,
    e2e_humanless_ok: bool = False,
    ambiguous_ok: bool = False,
    completeness_ok: bool = False,
    failure_recovery_ok: bool = False,
    lesson_replay_ok: bool = False,
    regression_ok: bool = False,
    g3_hard_ok: bool = False,
) -> AutonomyScorecard:
    """Weighted score; AUTONOMY 8+ VERIFIED only if all mandatory proofs pass."""
    gm = gate_map or {}
    passed_levels = {r.level for r in level_results if r.status == LevelStatus.PASS}
    failed_levels = {r.level for r in level_results if r.status == LevelStatus.FAIL}

    def lvl_pass(n: int) -> bool:
        return n in passed_levels

    criteria = [
        CriterionScore(
            1,
            "Hata tespiti",
            8.5 if self_review_ok and domain_invariants_ok else (7.0 if self_review_ok else 5.0),
            0.10,
            evidence=[f"self_review_ok={self_review_ok}", f"domain_invariants_ok={domain_invariants_ok}"],
            test_ids=["tests/test_domain_invariants.py", "tests/test_autonomy_protocol.py::test_self_review_catches_syntax"],
            limit="Coverage-bound for unseen domains",
        ),
        CriterionScore(
            2,
            "Hata düzeltme",
            8.5 if failure_recovery_ok and baseline_fail == 0 else (7.0 if baseline_fail == 0 else 4.5),
            0.10,
            evidence=[f"baseline_pass={baseline_pass}", f"baseline_fail={baseline_fail}", f"failure_recovery_ok={failure_recovery_ok}"],
            test_ids=["tests/test_verify8_challenges.py::test_failure_recovery_loop_records_minimal_patch"],
            limit="Ambiguous product decisions still need humans",
        ),
        CriterionScore(
            3,
            "Completeness",
            8.5 if completeness_ok else 6.0,
            0.10,
            evidence=[f"completeness_ok={completeness_ok}"],
            test_ids=["tests/test_verify8_challenges.py::test_completeness_reliability_surfaces"],
            limit="Dynamic dispatch may hide call sites",
        ),
        CriterionScore(
            4,
            "Gerçek test çalıştırma",
            9.0 if baseline_pass >= 300 and gates_ok else 7.0,
            0.10,
            evidence=[f"pytest_pass≈{baseline_pass}", f"gates_ok={gates_ok}"],
            test_ids=["autonomy/evidence/verify8_baseline_full.txt"],
            limit="Some live HTTP smokes are environment-dependent",
        ),
        CriterionScore(
            5,
            "Root-cause/recovery",
            8.5 if failure_recovery_ok and lvl_pass(4) else 6.0,
            0.10,
            evidence=[f"failure_recovery_ok={failure_recovery_ok}", f"L4={lvl_pass(4)}"],
            test_ids=["tests/test_verify8_challenges.py::test_failure_recovery_injected_bug_caught_by_regression"],
            limit="Hypothesis quality still human-auditable",
        ),
        CriterionScore(
            6,
            "Kalıcı öğrenme",
            8.5 if lesson_replay_ok and lesson_count >= 5 else 6.0,
            0.10,
            evidence=[f"lesson_count={lesson_count}", f"lesson_replay_ok={lesson_replay_ok}"],
            test_ids=["tests/test_verify8_challenges.py::test_lesson_store_catches_repeated_error_class"],
            limit="No self-modifying production code (by design)",
        ),
        CriterionScore(
            7,
            "Görev parçalama",
            8.0 if gates_ok and e2e_humanless_ok else 6.5,
            0.10,
            evidence=["LOOP_STEPS", f"e2e_humanless_ok={e2e_humanless_ok}"],
            test_ids=["tests/test_verify8_challenges.py::test_e2e_reliability_gate_blocks_unreliable_md"],
            limit="Scope creep still possible on vague briefs",
        ),
        CriterionScore(
            8,
            "Level progression",
            8.5 if passed_levels >= {1, 2, 3, 4, 5, 6, 7, 8} else 5.0,
            0.10,
            evidence=[f"passed={sorted(passed_levels)}", f"failed={sorted(failed_levels)}"],
            test_ids=["tests/test_level_gates.py", "tests/test_level7.py", "tests/test_level8.py"],
            limit="L8 = research/paper acceptance, not LIVE trading autonomy",
        ),
        CriterionScore(
            9,
            "Mimari karar/refactor",
            8.0 if g3_hard_ok and completeness_ok else 6.0,
            0.10,
            evidence=[f"g3_hard_ok={g3_hard_ok}", "scoped mypy + reliability gate seam"],
            test_ids=["tests/test_verify8_challenges.py::test_g3_typecheck_is_hard_pass", "mypy.ini"],
            limit="Not a whole-repo rewrite",
        ),
        CriterionScore(
            10,
            "İnsan müdahalesiz E2E",
            8.5 if e2e_humanless_ok and ambiguous_ok and live_locked else 5.5,
            0.10,
            evidence=[
                f"e2e_humanless_ok={e2e_humanless_ok}",
                f"ambiguous_ok={ambiguous_ok}",
                f"live_locked={live_locked}",
            ],
            test_ids=[
                "tests/test_verify8_challenges.py::test_e2e_reliability_gate_blocks_unreliable_md",
                "tests/test_verify8_challenges.py::test_e2e_service_scan_empty_when_unreliable",
            ],
            limit="Safety/product gates may still ask humans — that is correct",
        ),
    ]

    overall = round(sum(c.score * c.weight for c in criteria) / sum(c.weight for c in criteria) * 10, 2)
    # criteria already 0-10; weighted average of scores:
    overall = round(sum(c.score * c.weight for c in criteria), 2)

    mandatory = {
        "G1": bool(gm.get("G1_syntax_import", gates_ok)),
        "G2": bool(gm.get("G2_lint", gates_ok)),
        "G3_HARD": bool(g3_hard_ok or gm.get("G3_typecheck", False)),
        "G4": bool(gm.get("G4_unit", gates_ok)),
        "G5": bool(gm.get("G5_integration", gates_ok)),
        "G6": bool(gm.get("G6_regression", regression_ok or gates_ok)),
        "G7": bool(gm.get("G7_smoke", gates_ok)),
        "G8": bool(gm.get("G8_self_review", self_review_ok)),
        "domain_invariants": domain_invariants_ok,
        "completeness": completeness_ok,
        "failure_recovery": failure_recovery_ok,
        "e2e_humanless": e2e_humanless_ok,
        "regression": regression_ok or baseline_fail == 0,
        "live_locked": live_locked,
    }
    all_mandatory = all(mandatory.values())

    if not live_locked:
        verdict = "AUTONOMY SCORE INCONCLUSIVE"
        notes = ["LIVE lock failed — scoring aborted"]
        overall = min(overall, 3.0)
    elif all_mandatory and overall >= 8.0:
        verdict = "AUTONOMY 8+ VERIFIED"
        notes = [
            "All mandatory verify-8 proofs PASS",
            "Meaning: coding/validation autonomy — NOT live-money trading autonomy",
        ]
    elif baseline_pass < 50:
        verdict = "AUTONOMY SCORE INCONCLUSIVE"
        notes = ["Insufficient pytest evidence"]
    else:
        missing = [k for k, v in mandatory.items() if not v]
        verdict = "AUTONOMY 8+ NOT VERIFIED"
        notes = [
            f"overall={overall}",
            f"mandatory_missing={missing}",
            "8+ withheld until all mandatory proofs pass",
        ]

    return AutonomyScorecard(
        overall=overall,
        criteria=criteria,
        level_results=[r.to_dict() for r in level_results],
        verdict=verdict,
        starting=5.6,
        notes=notes,
        mandatory=mandatory,
    )
