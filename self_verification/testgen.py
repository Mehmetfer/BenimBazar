"""GÖREV 25 — Automated regression test generation with quality gates."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GeneratedTest:
    name: str
    source: str
    problem: str
    expected_behavior: str
    quality: Dict[str, bool] = field(default_factory=dict)
    accepted: bool = False
    rejection_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "problem": self.problem,
            "expected_behavior": self.expected_behavior,
            "quality": dict(self.quality),
            "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
        }


def _has_assert(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("assert"):
                return True
    return False


def evaluate_test_quality(source: str) -> tuple[Dict[str, bool], List[str]]:
    reasons: List[str] = []
    quality = {
        "syntax": False,
        "isolation": False,
        "determinism": False,
        "assertion_quality": False,
    }
    try:
        tree = ast.parse(source)
        quality["syntax"] = True
    except SyntaxError as exc:
        reasons.append(f"syntax_error:{exc}")
        return quality, reasons

    # Isolation: no network / subprocess / sleep
    banned = {"requests", "urllib", "socket", "subprocess", "time.sleep", "random.random"}
    src_l = source.lower()
    if any(b.split(".")[-1] in src_l and b.replace(".", "") in src_l.replace(".", "") for b in banned):
        # simpler checks:
        pass
    if "subprocess" in source or "requests." in source or "urllib" in source:
        reasons.append("non_isolated_io")
    else:
        quality["isolation"] = True

    if "random.random" in source or "time.time()" in source or "datetime.now" in source:
        reasons.append("non_deterministic")
    else:
        quality["determinism"] = True

    if _has_assert(tree):
        quality["assertion_quality"] = True
    else:
        reasons.append("missing_assertion")

    return quality, reasons


def generate_regression_test(
    *,
    problem: str,
    expected_behavior: str,
    function_under_test: str = "self_check",
) -> GeneratedTest:
    """Problem → Expected Behavior → Regression Test (quality-gated)."""
    name = "test_generated_regression_" + "".join(c if c.isalnum() else "_" for c in problem.lower())[:40]
    source = f'''"""Auto-generated regression test — must pass quality gates."""
from module import {function_under_test}


def {name}():
    # Expected: {expected_behavior}
    # Problem: {problem}
    result = {function_under_test}()
    assert result is True, "expected_behavior: {expected_behavior}"
'''
    quality, reasons = evaluate_test_quality(source)
    accepted = all(quality.values())
    if not accepted and not reasons:
        reasons.append("quality_gate_failed")
    return GeneratedTest(
        name=name,
        source=source,
        problem=problem,
        expected_behavior=expected_behavior,
        quality=quality,
        accepted=accepted,
        rejection_reasons=reasons,
    )


def generate_bad_test_example() -> GeneratedTest:
    """Intentionally low-quality test — must NOT be accepted as PASS evidence."""
    source = "def test_bad():\n    x = 1 + 1\n"
    quality, reasons = evaluate_test_quality(source)
    return GeneratedTest(
        name="test_bad",
        source=source,
        problem="demo",
        expected_behavior="none",
        quality=quality,
        accepted=all(quality.values()),
        rejection_reasons=reasons or ["missing_assertion"],
    )
