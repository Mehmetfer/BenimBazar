"""FAZ 5 — Failure protocol: one hypothesis → one patch → retest."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class FailureCase:
    test_node: str
    failure_excerpt: str
    hypothesis: str = ""
    root_cause: str = ""
    patch_summary: str = ""
    retest_ok: bool | None = None
    regression_nodes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def begin_failure_analysis(test_node: str, failure_excerpt: str) -> FailureCase:
    return FailureCase(test_node=test_node, failure_excerpt=failure_excerpt[:4000])


def record_hypothesis(case: FailureCase, hypothesis: str) -> FailureCase:
    case.hypothesis = hypothesis.strip()
    return case


def record_root_cause(case: FailureCase, root_cause: str) -> FailureCase:
    case.root_cause = root_cause.strip()
    return case


def record_patch(case: FailureCase, patch_summary: str) -> FailureCase:
    case.patch_summary = patch_summary.strip()
    return case


def record_retest(case: FailureCase, ok: bool, *, regression_nodes: list[str] | None = None) -> FailureCase:
    case.retest_ok = bool(ok)
    if regression_nodes:
        case.regression_nodes = list(regression_nodes)
    return case


def protocol_steps() -> list[str]:
    return [
        "1. Read full failure",
        "2. State one hypothesis",
        "3. Minimal reproducible case",
        "4. Identify root cause",
        "5. Apply one minimal patch",
        "6. Re-run same test",
        "7. Run related regression tests",
        "8. Optionally full suite",
        "9. Verify no collateral breakage",
    ]
