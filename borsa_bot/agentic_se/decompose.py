"""Task decomposition — goal → requirements → tasks → acceptance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SubTask:
    id: str
    title: str
    kind: str  # discover|implement|test|review|verify
    target_hints: list[str] = field(default_factory=list)
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskPlan:
    goal: str
    requirements: list[str]
    affected_modules: list[str]
    dependencies: list[str]
    risks: list[str]
    tasks: list[SubTask]
    acceptance: list[str]
    unknown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "requirements": self.requirements,
            "affected_modules": self.affected_modules,
            "dependencies": self.dependencies,
            "risks": self.risks,
            "tasks": [t.to_dict() for t in self.tasks],
            "acceptance": self.acceptance,
            "unknown": self.unknown,
        }


def decompose_goal(goal: str, *, repo_packages: list[str] | None = None) -> TaskPlan:
    """Heuristic decomposition (evidence-seeking; marks UNKNOWN when unsure)."""
    g = goal.strip()
    gl = g.lower()
    packages = repo_packages or []
    affected: list[str] = []
    unknown: list[str] = []

    keyword_map = {
        "provider": ["crypto/providers", "data/", "autonomous/recovery"],
        "recovery": ["autonomous/recovery", "trading_safety/restart", "self_improvement"],
        "idempotency": ["trading_safety/idempotency", "trading_safety/pipeline"],
        "risk": ["risk/", "trading_safety/order_gate"],
        "test": ["tests/"],
        "autonomy": ["autonomy/", "self_improvement/", "agentic_se/"],
        "agentic": ["agentic_se/"],
        "memory": ["agentic_se/discovery.py", "agentic_se/data"],
        "benchmark": ["agentic_se/benchmarks.py"],
        "baseline": ["self_improvement/baseline_guard.py", "self_improvement/verify.py"],
    }
    for key, paths in keyword_map.items():
        if key in gl:
            affected.extend(paths)

    # Prefer existing packages that match
    for pkg in packages:
        pl = pkg.lower()
        if any(k in gl for k in pl.split("/") if len(k) > 3):
            if pkg not in affected:
                affected.append(pkg)

    if not affected:
        unknown.append("affected modules not confidently determined from goal text")
        affected = ["agentic_se/", "tests/"]

    risks = []
    if any(x in gl for x in ("risk", "broker", "live", "kill", "execution")):
        risks.append("HIGH — trading-critical surface; expanded regression required")
    else:
        risks.append("MODERATE — stay on allowlist; no safety bypass")

    tasks = [
        SubTask("T1", "Repository discovery / memory refresh", "discover", ["agentic_se/discovery.py"]),
        SubTask("T2", "Locate implementation + tests", "discover", affected[:5]),
        SubTask("T3", "Implement minimal change", "implement", affected[:5]),
        SubTask("T4", "Add/adjust tests (TDD if bugfix)", "test", ["tests/"]),
        SubTask("T5", "Run tests + typecheck", "verify", ["tests/"]),
        SubTask("T6", "Self-review + quality gate", "review", []),
    ]

    requirements = [
        f"Satisfy goal: {g}",
        "Do not delete tests or weaken assertions to pass",
        "Preserve trading domain invariants",
        "Keep changes minimal, targeted, reversible",
    ]
    acceptance = [
        "New/changed tests pass",
        "No baseline regression on scoped suite",
        "Quality gate checklist complete",
        "No forbidden safety mutations",
    ]
    return TaskPlan(
        goal=g,
        requirements=requirements,
        affected_modules=affected,
        dependencies=["pytest", "mypy (scoped)"],
        risks=risks,
        tasks=tasks,
        acceptance=acceptance,
        unknown=unknown,
    )
