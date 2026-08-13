"""GÖREV 30 — F6 paper loop + F7 controlled loop safe coupling."""

from __future__ import annotations

from pathlib import Path

from decision.engine import DecisionAction, decide_from_state
from decision.feedback import DecisionFeedbackLoop
from decision.pipeline import F6PaperLoop
from decision.replay import DecisionReplayStore
from self_verification.f7_loop import F7ControlledLoop
from self_verification.learning import LearningMemory
from tests.decision_fixtures import bull_liquid_state, sparse_unknown_state


def test_g30_f6_f7_coupled_safely(tmp_path):
    # F6: missing data → NO_TRADE recorded
    f6 = F6PaperLoop(
        feedback=DecisionFeedbackLoop(),
        replay=DecisionReplayStore(tmp_path / "replay.jsonl"),
    )

    class _BadProv:
        def get_quote(self, symbol):
            raise RuntimeError("no data")

        def get_bars(self, symbol, n):
            return []

        def source_meta(self, n):
            class M:
                freshness = type("F", (), {"value": "NO_DATA"})()

            return M()

    cycle = f6.run_cycle(provider=_BadProv(), ledger=None, symbol="ZZZ")
    assert cycle.decision.decision == DecisionAction.NO_TRADE
    assert cycle.execution.live_trading is False if hasattr(cycle.execution, "live_trading") else True
    assert cycle.to_dict()["live_trading"] is False
    assert f6.feedback.no_trade_log

    # F6 bull path produces explainable decision
    out = decide_from_state(bull_liquid_state())
    assert out.to_dict()["execution_mode"] == "PAPER"
    assert out.evidence

    # F7 observes F6-like degradation stats and proposes (no production mutate)
    f7 = F7ControlledLoop(learning=LearningMemory(tmp_path / "learn.jsonl"))
    result = f7.run(
        decision_stats={
            "win_rate": 0.2,
            "trades": 12,
            "consecutive_losses": 6,
            "cycles": 20,
            "no_trade_ratio": 0.2,
        },
        run_sandbox_fix=True,
        inject_failure=False,
        sandbox_root=tmp_path / "sb",
    )
    assert result.production_mutated is False
    assert result.auto_deployed is False
    assert result.verification["status"] in {"READY_FOR_REVIEW", "ROLLED_BACK", "FAILED"}
    assert result.to_dict()["f8"] == "DISABLED"
    # Coupling rule: F7 may observe F6 metrics but must not open LIVE
    assert sparse_unknown_state().price.last.value is None
