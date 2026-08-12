"""Autonomous error recovery — hypothesis → patch → retest (bounded)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from autonomy.failure import begin_failure_analysis, record_hypothesis, record_patch, record_retest, record_root_cause


@dataclass
class RepairAttempt:
    hypothesis: str
    patch_summary: str
    retest_ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepairResult:
    ok: bool
    attempts: list[RepairAttempt] = field(default_factory=list)
    root_cause: str = ""
    exhausted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "attempts": [a.to_dict() for a in self.attempts],
            "root_cause": self.root_cause,
            "exhausted": self.exhausted,
        }


PatchFn = Callable[[str, int], tuple[bool, str, str]]  # failure, attempt_idx -> (applied, summary, new_failure_or_empty)
RetestFn = Callable[[], tuple[bool, str]]


def repair_loop(
    *,
    failure_excerpt: str,
    test_node: str,
    apply_patch: PatchFn,
    retest: RetestFn,
    max_iterations: int = 3,
) -> RepairResult:
    """TEST FAILURE → READ → HYPOTHESIS → PATCH → RETEST (no assertion-weakening)."""
    if "assert" in failure_excerpt.lower() and "delete" in failure_excerpt.lower():
        # heuristic: refuse test deletion narratives
        return RepairResult(ok=False, root_cause="refusing test deletion", exhausted=True)

    case = begin_failure_analysis(test_node, failure_excerpt)
    attempts: list[RepairAttempt] = []
    current_failure = failure_excerpt

    hypotheses = [
        "implementation bug at primary call site",
        "missing edge-case handling / off-by-one",
        "stale state or incorrect fixture wiring",
    ]

    for i in range(max_iterations):
        hyp = hypotheses[i % len(hypotheses)]
        record_hypothesis(case, hyp)
        applied, summary, residual = apply_patch(current_failure, i)
        record_patch(case, summary)
        if not applied:
            attempts.append(RepairAttempt(hyp, summary, False, residual or "patch not applied"))
            continue
        ok, detail = retest()
        record_retest(case, ok)
        attempts.append(RepairAttempt(hyp, summary, ok, detail[-500:]))
        if ok:
            record_root_cause(case, f"resolved under hypothesis: {hyp}")
            return RepairResult(ok=True, attempts=attempts, root_cause=case.root_cause)
        current_failure = detail or residual or current_failure

    return RepairResult(
        ok=False,
        attempts=attempts,
        root_cause="unresolved within MAX_ITERATIONS",
        exhausted=True,
    )
