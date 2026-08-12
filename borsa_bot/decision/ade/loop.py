"""Humanless autonomous trading loop — observe → … → continue (no WAIT FOR HUMAN)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4

from decision.ade.chain import MarketSnapshot
from decision.ade.engine import AutonomousDecisionEngine
from decision.ade.limits import ImmutableSafetyLimits
from decision.ade.states import DecisionAction
from trading_safety.modes import TradingExecutionMode
from trading_safety.pipeline import SafeExecutionPipeline


SnapshotFactory = Callable[[], MarketSnapshot]


@dataclass
class LoopCycleReport:
    cycle_id: str
    action: str
    waited_for_human: bool
    decision: dict[str, Any]
    continue_loop: bool
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoopRunReport:
    cycles: list[LoopCycleReport] = field(default_factory=list)
    human_waits: int = 0
    trades: int = 0
    no_trades: int = 0
    halted: bool = False
    note: str = "HUMANLESS loop — PAPER/SHADOW only; LIVE-MONEY AUTONOMY not claimed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles": [c.to_dict() for c in self.cycles],
            "human_waits": self.human_waits,
            "trades": self.trades,
            "no_trades": self.no_trades,
            "halted": self.halted,
            "note": self.note,
        }


class AutonomousTradingLoop:
    """Runs N cycles without human approval. Fail-closed on unsafe/unknown."""

    def __init__(
        self,
        engine: AutonomousDecisionEngine | None = None,
        *,
        limits: ImmutableSafetyLimits | None = None,
        pipeline: SafeExecutionPipeline | None = None,
        mode: TradingExecutionMode = TradingExecutionMode.PAPER,
    ) -> None:
        limits = limits or ImmutableSafetyLimits(live_broker_enabled=False)
        self.engine = engine or AutonomousDecisionEngine(limits=limits, pipeline=pipeline, mode=mode)

    def run_cycle(
        self,
        snap: MarketSnapshot,
        *,
        execute: bool = True,
        alternate: dict[str, Any] | None = None,
    ) -> LoopCycleReport:
        cid = f"loop-{uuid4().hex[:10]}"
        rec = self.engine.decide(snap, cycle_id=cid, execute=execute, alternate_provider=alternate)
        assert rec.waited_for_human is False
        return LoopCycleReport(
            cycle_id=cid,
            action=rec.action,
            waited_for_human=False,
            decision=rec.to_dict(),
            continue_loop=not self.engine.halted,
            mode=self.engine.mode.value,
        )

    def run(
        self,
        snapshots: list[MarketSnapshot] | SnapshotFactory,
        *,
        n: int = 1,
        execute: bool = True,
        alternate_for: Optional[Callable[[MarketSnapshot], dict[str, Any] | None]] = None,
    ) -> LoopRunReport:
        report = LoopRunReport()
        for i in range(n):
            if self.engine.halted:
                report.halted = True
                break
            snap = snapshots() if callable(snapshots) else snapshots[i % len(snapshots)]
            alt = alternate_for(snap) if alternate_for else None
            cyc = self.run_cycle(snap, execute=execute, alternate=alt)
            report.cycles.append(cyc)
            if not cyc.continue_loop:
                report.halted = True
                break

        report.trades = sum(1 for c in report.cycles if c.decision.get("execution", {}).get("ok") is True)
        report.no_trades = sum(1 for c in report.cycles if c.action == DecisionAction.NO_TRADE.value)
        report.human_waits = sum(1 for c in report.cycles if c.waited_for_human)
        return report
