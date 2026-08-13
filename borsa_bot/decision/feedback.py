"""GÖREV 17–19 — Paper feedback, strategy memory, calibration status for decision loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class CalibrationStatus(str, Enum):
    CALIBRATED = "CALIBRATED"
    OVERCONFIDENT = "OVERCONFIDENT"
    UNDERCONFIDENT = "UNDERCONFIDENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class PaperTradeResult:
    symbol: str
    decision: str
    confidence: float
    pnl: float
    won: bool
    regime: str = "UNKNOWN"
    strategy: str = "ensemble"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lesson: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision": self.decision,
            "confidence": self.confidence,
            "pnl": self.pnl,
            "won": self.won,
            "regime": self.regime,
            "strategy": self.strategy,
            "timestamp": self.timestamp,
            "lesson": self.lesson,
        }


@dataclass
class StrategyMemoryRow:
    strategy: str
    market_regime: str
    signal_type: str
    confidence_bucket: str
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    gross_win: float = 0.0
    gross_loss: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    peak: float = 0.0
    equity_curve: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trade_count if self.trade_count else 0.0

    @property
    def loss_rate(self) -> float:
        return self.losses / self.trade_count if self.trade_count else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss <= 1e-9:
            return 9.9 if self.gross_win > 0 else 0.0
        return self.gross_win / self.gross_loss

    @property
    def average_return(self) -> float:
        return self.total_return / self.trade_count if self.trade_count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "market_regime": self.market_regime,
            "signal_type": self.signal_type,
            "confidence_bucket": self.confidence_bucket,
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate, 4),
            "loss_rate": round(self.loss_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "drawdown": round(self.max_drawdown, 4),
            "average_return": round(self.average_return, 4),
        }


@dataclass
class ProposedUpdate:
    """Safe proposal only — never auto-mutates live strategy weights."""

    kind: str = "PROPOSED_UPDATE"
    strategy: str = ""
    rationale: str = ""
    suggested_weight_delta: float = 0.0
    auto_applied: bool = False
    requires_human_approval: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "strategy": self.strategy,
            "rationale": self.rationale,
            "suggested_weight_delta": self.suggested_weight_delta,
            "auto_applied": False,
            "requires_human_approval": True,
        }


def confidence_bucket(confidence: float) -> str:
    """confidence may be 0–1 or 0–100."""
    c = float(confidence)
    if c <= 1.0:
        c *= 100.0
    if c >= 90:
        return "90+"
    if c >= 70:
        return "70-89"
    if c >= 60:
        return "60-69"
    return "0-59"


@dataclass
class DecisionFeedbackLoop:
    """
    DECISION → PAPER EXECUTION → RESULT → P&L → RISK → LESSON → NEXT DECISION

    Lessons influence the next decision via calibration_hint + strategy_memory_hint
    and size_multiplier — not via silent production weight mutation.
    """

    results: List[PaperTradeResult] = field(default_factory=list)
    no_trade_log: List[Dict[str, Any]] = field(default_factory=list)
    memory: Dict[str, StrategyMemoryRow] = field(default_factory=dict)
    proposed_updates: List[ProposedUpdate] = field(default_factory=list)
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    # Calibration buckets: predicted confidence band → outcomes
    cal_buckets: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: {
            "90+": {"n": 0, "wins": 0},
            "70-89": {"n": 0, "wins": 0},
            "60-69": {"n": 0, "wins": 0},
            "0-59": {"n": 0, "wins": 0},
        }
    )

    def record_no_trade(self, decision: Dict[str, Any]) -> None:
        self.no_trade_log.append(
            {
                "timestamp": decision.get("timestamp"),
                "symbol": decision.get("symbol"),
                "reason": decision.get("reason"),
                "no_trade_reasons": decision.get("no_trade_reasons", []),
                "confidence": decision.get("confidence"),
                "execution_mode": "PAPER",
            }
        )

    def record_result(
        self,
        *,
        symbol: str,
        decision: str,
        confidence: float,
        pnl: float,
        regime: str = "UNKNOWN",
        strategy: str = "ensemble",
        signal_type: str = "COMPOSITE",
    ) -> PaperTradeResult:
        won = pnl > 0
        lesson = self._lesson(won, pnl, regime, confidence)
        row = PaperTradeResult(
            symbol=symbol,
            decision=decision,
            confidence=confidence,
            pnl=pnl,
            won=won,
            regime=regime,
            strategy=strategy,
            lesson=lesson,
        )
        self.results.append(row)
        self.daily_pnl += float(pnl)
        if won:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        bucket = confidence_bucket(confidence)
        self.cal_buckets[bucket]["n"] += 1
        if won:
            self.cal_buckets[bucket]["wins"] += 1

        key = f"{strategy}|{regime}|{signal_type}|{bucket}"
        mem = self.memory.setdefault(
            key,
            StrategyMemoryRow(
                strategy=strategy,
                market_regime=regime,
                signal_type=signal_type,
                confidence_bucket=bucket,
            ),
        )
        mem.trade_count += 1
        mem.total_return += float(pnl)
        mem.equity_curve += float(pnl)
        mem.peak = max(mem.peak, mem.equity_curve)
        dd = mem.peak - mem.equity_curve
        mem.max_drawdown = max(mem.max_drawdown, dd)
        if won:
            mem.wins += 1
            mem.gross_win += float(pnl)
        else:
            mem.losses += 1
            mem.gross_loss += abs(float(pnl))

        proposal = self._maybe_propose_update(mem)
        if proposal:
            self.proposed_updates.append(proposal)
        return row

    def _lesson(self, won: bool, pnl: float, regime: str, confidence: float) -> str:
        if won:
            return f"positive_outcome regime={regime} conf={confidence:.2f}"
        if regime in ("HIGH_VOLATILITY", "LOW_LIQUIDITY"):
            return f"avoid_trade_in_{regime.lower()}"
        if confidence >= 0.8 and pnl < 0:
            return "high_confidence_loss_reduce_size"
        return "review_signal_quality"

    def _maybe_propose_update(self, mem: StrategyMemoryRow) -> Optional[ProposedUpdate]:
        if mem.trade_count < 5:
            return None
        if mem.win_rate < 0.4 and mem.average_return < 0:
            return ProposedUpdate(
                strategy=mem.strategy,
                rationale=(
                    f"PROPOSED_UPDATE: {mem.strategy} underperforms in {mem.market_regime} "
                    f"(wr={mem.win_rate:.2f}, n={mem.trade_count}). Human approval required."
                ),
                suggested_weight_delta=-0.1,
            )
        if mem.win_rate > 0.6 and mem.profit_factor > 1.4:
            return ProposedUpdate(
                strategy=mem.strategy,
                rationale=(
                    f"PROPOSED_UPDATE: {mem.strategy} strong in {mem.market_regime} "
                    f"(wr={mem.win_rate:.2f}, pf={mem.profit_factor:.2f}). Human approval required."
                ),
                suggested_weight_delta=0.05,
            )
        return None

    def calibration_status(self) -> CalibrationStatus:
        hi = self.cal_buckets["90+"]
        mid = self.cal_buckets["60-69"]
        total_n = sum(b["n"] for b in self.cal_buckets.values())
        if total_n < 8 or hi["n"] < 3:
            return CalibrationStatus.INSUFFICIENT_DATA
        hi_rate = hi["wins"] / hi["n"] if hi["n"] else 0.0
        mid_rate = mid["wins"] / mid["n"] if mid["n"] else 0.5
        # Expected: high confidence should win more often
        if hi_rate + 0.05 < mid_rate or hi_rate < 0.45:
            return CalibrationStatus.OVERCONFIDENT
        if hi_rate > 0.75 and mid_rate < 0.4:
            return CalibrationStatus.UNDERCONFIDENT
        if abs(hi_rate - 0.85) < 0.2:
            return CalibrationStatus.CALIBRATED
        return CalibrationStatus.CALIBRATED

    def calibration_evidence(self) -> Dict[str, Any]:
        status = self.calibration_status()
        return {
            "status": status.value,
            "buckets": {
                k: {
                    "n": v["n"],
                    "wins": v["wins"],
                    "hit_rate": round(v["wins"] / v["n"], 4) if v["n"] else None,
                }
                for k, v in self.cal_buckets.items()
            },
            "feeds_decision": True,
        }

    def strategy_memory_hint(self, strategy: str = "ensemble", regime: str = "UNKNOWN") -> Optional[str]:
        rows = [m for m in self.memory.values() if m.strategy == strategy and m.market_regime == regime]
        if not rows:
            rows = [m for m in self.memory.values() if m.strategy == strategy]
        if not rows:
            return None
        worst = min(rows, key=lambda m: m.win_rate if m.trade_count >= 3 else 1.0)
        if worst.trade_count >= 3 and worst.win_rate < 0.4:
            return f"weak_history:{worst.market_regime}:{worst.win_rate:.2f}"
        return None

    def size_multiplier(self, strategy: str = "ensemble") -> float:
        rows = [m for m in self.memory.values() if m.strategy == strategy]
        if not rows:
            return 1.0
        total = sum(m.trade_count for m in rows)
        wins = sum(m.wins for m in rows)
        if total < 5:
            return 1.0
        wr = wins / total
        if wr < 0.35:
            return 0.0  # NO_TRADE path via size 0
        if wr < 0.45:
            return 0.5
        return 1.0

    def next_decision_context(self, strategy: str = "ensemble", regime: str = "UNKNOWN") -> Dict[str, Any]:
        """Evidence package consumed by the next decide_from_state call."""
        cal = self.calibration_status()
        return {
            "calibration_hint": cal.value,
            "strategy_memory_hint": self.strategy_memory_hint(strategy, regime),
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "size_multiplier": self.size_multiplier(strategy),
            "proposed_updates": [p.to_dict() for p in self.proposed_updates[-5:]],
            "lessons": [r.lesson for r in self.results[-5:]],
            "calibration_evidence": self.calibration_evidence(),
            "auto_weight_mutation": False,
        }

    def report(self) -> Dict[str, Any]:
        return {
            "trades": len(self.results),
            "no_trades_logged": len(self.no_trade_log),
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "calibration": self.calibration_evidence(),
            "memory": [m.to_dict() for m in self.memory.values()],
            "proposed_updates": [p.to_dict() for p in self.proposed_updates],
            "recent_lessons": [r.to_dict() for r in self.results[-10:]],
            "live_trading": False,
        }
