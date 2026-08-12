"""Autonomous quality gate checklist — must pass before DELIVER."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QualityGate:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QualityReport:
    ok: bool
    gates: list[QualityGate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "gates": [g.to_dict() for g in self.gates]}


def evaluate_quality(
    *,
    requirements_satisfied: bool,
    implementation_complete: bool,
    tests_added_when_needed: bool,
    existing_tests_pass: bool,
    new_tests_pass: bool,
    typecheck_pass: bool,
    lint_pass: bool = True,
    regression_pass: bool,
    security_reviewed: bool,
    domain_invariants_ok: bool,
    git_diff_reviewed: bool,
    no_destructive_unrelated: bool,
) -> QualityReport:
    items = [
        ("task requirements satisfied", requirements_satisfied),
        ("implementation complete", implementation_complete),
        ("tests added where needed", tests_added_when_needed),
        ("existing tests pass", existing_tests_pass),
        ("new tests pass", new_tests_pass),
        ("type checks pass", typecheck_pass),
        ("lint passes", lint_pass),
        ("regression passes", regression_pass),
        ("security reviewed", security_reviewed),
        ("domain invariants preserved", domain_invariants_ok),
        ("git diff reviewed", git_diff_reviewed),
        ("no unrelated destructive changes", no_destructive_unrelated),
    ]
    gates = [QualityGate(n, ok) for n, ok in items]
    return QualityReport(ok=all(g.ok for g in gates), gates=gates)
