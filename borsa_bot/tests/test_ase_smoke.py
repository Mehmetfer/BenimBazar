"""ASE smoke tests — safe nested verify targets."""

from __future__ import annotations

from agentic_se.boundaries import se_path_allowed
from agentic_se.decompose import decompose_goal
from agentic_se.discovery import discover_repository
from agentic_se.playground import buggy_add, clamp_non_negative


def test_smoke_playground():
    assert buggy_add(1, 1) == 2
    assert clamp_non_negative(-1) == 0


def test_smoke_discovery():
    repo = discover_repository()
    assert "agentic_se" in " ".join(repo.packages) or any("agentic_se" in p for p in repo.packages)


def test_smoke_decompose():
    plan = decompose_goal("Add agentic_se benchmark coverage")
    assert plan.tasks


def test_smoke_allowlist():
    assert se_path_allowed("agentic_se/engine.py")
    assert not se_path_allowed("trading_safety/kill_switch.py")
