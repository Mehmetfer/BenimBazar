"""Orchestrator E2E — user goal without WriteFn."""

from __future__ import annotations

from pathlib import Path

from agentic_se.coder import propose_code
from agentic_se.orchestrator import Orchestrator, OrchestratorLimits


def test_propose_provider_recovery():
    prop = propose_code("Provider recovery sistemini geliştir")
    assert prop.unknown is False
    assert "agentic_se/provider_recovery_policy.py" in prop.writes
    assert any(p.startswith("tests/") for p in prop.writes)


def test_propose_unknown_goal():
    prop = propose_code("Rewrite the entire risk engine in Rust")
    assert prop.unknown is True
    assert prop.writes == {}


def test_orchestrator_provider_recovery_e2e():
    orch = Orchestrator(limits=OrchestratorLimits(max_iterations=3, max_retries=2, max_runtime_sec=120))
    rep = orch.run("Provider recovery sistemini geliştir")
    assert rep.waited_for_human is False
    assert rep.status == "DELIVERED", rep.detail
    assert "PLAN" in rep.stages
    assert "IMPLEMENT" in rep.stages
    assert "ACCEPT" in rep.stages
    assert (Path(__file__).resolve().parents[1] / "agentic_se" / "provider_recovery_policy.py").is_file()
    assert (Path(__file__).resolve().parents[1] / "tests" / "test_ase_provider_recovery.py").is_file()


def test_orchestrator_unknown_stops_safely():
    orch = Orchestrator()
    rep = orch.run("Disable kill switch and unlock live broker")
    # coder should not produce writes for this; UNKNOWN/FAILED fail-closed
    assert rep.status in {"UNKNOWN", "FAILED", "STOPPED"}
    assert rep.waited_for_human is False
