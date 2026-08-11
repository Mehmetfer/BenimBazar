"""Decision packet + durable memory (audit-friendly)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.models import utc_now
from config.settings import ROOT
from decision.context import ContextPack
from decision.opportunity import RankedOpportunity
from decision.reason import ReasoningResult


@dataclass
class DecisionPacket:
    decision_id: str
    timestamp: str
    market_type: str
    symbol: str
    action: str
    confidence: float | None
    probability: float | None
    regime: str | None
    strategy: str
    timeframes: dict[str, Any]
    opportunity_score: float
    expected_return: float | None
    expected_risk: float | None
    expected_value: float | None
    entry: float | None
    stop: float | None
    target: float | None
    risk_reward: float | None
    reason_codes: list[str]
    invalidations: list[str]
    counter_argument: str | None
    tree_path: list[str]
    model_version: str
    risk_engine_bypassed: bool = False  # MUST remain False
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    note: str = "AI proposes; RiskEngine decides permission"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_decision_packet(
    *,
    reasoning: ReasoningResult,
    context: ContextPack,
    opportunity: RankedOpportunity,
    row: dict[str, Any] | None = None,
    alternatives: list[RankedOpportunity] | None = None,
    model_version: str = "heuristic_ensemble",
) -> DecisionPacket:
    row = row or {}
    plan = row.get("ai_trade_plan") if isinstance(row.get("ai_trade_plan"), dict) else {}
    if not plan and isinstance(row.get("trade_plan"), dict):
        plan = row["trade_plan"]
    entry = row.get("entry") or plan.get("entry") or plan.get("entry_zone") or row.get("price")
    stop = row.get("stop") or plan.get("stop_loss") or plan.get("stop")
    target = None
    if row.get("targets"):
        target = row["targets"][0]
    if target is None:
        t1 = plan.get("target1")
        target = t1.get("price") if isinstance(t1, dict) else (t1 or plan.get("target_1"))

    alts = []
    for a in alternatives or []:
        if a.symbol == opportunity.symbol:
            continue
        alts.append(
            {
                "symbol": a.symbol,
                "rank": a.rank,
                "opportunity_score": a.opportunity_score,
                "expected_value": a.expected_value,
                "why_not_chosen": a.why_worse or a.why_better,
            }
        )

    return DecisionPacket(
        decision_id=reasoning.decision_id,
        timestamp=utc_now().isoformat(),
        market_type=reasoning.market_type,
        symbol=reasoning.symbol,
        action=reasoning.action,
        confidence=reasoning.confidence,
        probability=None,
        regime=reasoning.regime,
        strategy=reasoning.strategy,
        timeframes=opportunity.mtf,
        opportunity_score=reasoning.opportunity_score,
        expected_return=reasoning.expected_return_pct,
        expected_risk=reasoning.expected_risk_pct,
        expected_value=reasoning.expected_value,
        entry=float(entry) if entry is not None else None,
        stop=float(stop) if stop is not None else None,
        target=float(target) if target is not None else None,
        risk_reward=reasoning.risk_reward,
        reason_codes=list(reasoning.reason_codes),
        invalidations=list(reasoning.invalidations),
        counter_argument=reasoning.counter_argument,
        tree_path=list(reasoning.tree_path),
        model_version=model_version,
        risk_engine_bypassed=False,
        alternatives=alts[:5],
        context_snapshot={
            "regime": context.market_regime,
            "data_kind": context.data_kind,
            "data_fresh": context.data_fresh,
            "equity": context.equity,
            "drawdown_pct": context.drawdown_pct,
            "open_positions": context.open_positions,
            "unknowns": context.unknowns,
        },
    )


class DecisionMemory:
    """Durable decision memory — outcomes link later; no self-modifying code."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "ai_decisions.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path), timeout=30)

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_decisions (
                        decision_id TEXT PRIMARY KEY,
                        ts TEXT NOT NULL,
                        market_type TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        action TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        outcome TEXT,
                        outcome_at TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ai_dec_sym ON ai_decisions(symbol, ts)"
                )

    def record(self, packet: DecisionPacket) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ai_decisions
                    (decision_id, ts, market_type, symbol, action, payload, outcome, outcome_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        packet.decision_id,
                        packet.timestamp,
                        packet.market_type,
                        packet.symbol,
                        packet.action,
                        json.dumps(packet.to_dict(), ensure_ascii=False),
                    ),
                )

    def recent(self, *, symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            with self._conn() as conn:
                if symbol:
                    cur = conn.execute(
                        "SELECT payload, outcome FROM ai_decisions WHERE symbol=? ORDER BY ts DESC LIMIT ?",
                        (symbol.upper(), int(limit)),
                    )
                else:
                    cur = conn.execute(
                        "SELECT payload, outcome FROM ai_decisions ORDER BY ts DESC LIMIT ?",
                        (int(limit),),
                    )
                rows = cur.fetchall()
        out = []
        for payload, outcome in rows:
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            d["outcome"] = outcome
            out.append(d)
        return out

    def mark_outcome(self, decision_id: str, outcome: str) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE ai_decisions SET outcome=?, outcome_at=? WHERE decision_id=?",
                    (outcome, utc_now().isoformat(), decision_id),
                )


def new_decision_id() -> str:
    return f"AID-{uuid4().hex[:12]}"
