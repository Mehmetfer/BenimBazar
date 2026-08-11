"""TechnicalAgent + QuantAgent — structured views over existing scan row features."""

from __future__ import annotations

import time
from typing import Any

from decision.agents import AgentResult, BaseAgent


class TechnicalAgent(BaseAgent):
    agent_id = "TechnicalAgent"

    def run(self, row: dict[str, Any]) -> AgentResult:
        t0 = time.perf_counter()
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        mtf = row.get("mtf") if isinstance(row.get("mtf"), dict) else {}
        # Deduplicate correlated evidence: treat RSI/MACD/EMA family as one "trend_momentum" bucket
        evidence = {
            "trend_momentum": float(scores.get("technical") or scores.get("momentum") or 0),
            "volume_confirmation": float(scores.get("volume") or 0),
            "mtf": mtf,
            "regime": row.get("regime"),
        }
        # Do not double-count momentum + technical if both present — already merged above
        strength = evidence["trend_momentum"]
        vol_ok = evidence["volume_confirmation"] >= 55
        return AgentResult(
            self.agent_id,
            True,
            {
                "evidence": evidence,
                "direction": _dir_from_action(row),
                "confidence": float(row.get("ai_confidence") or strength or 0),
                "volume_ok": vol_ok,
                "note": "Correlated indicators counted once (trend_momentum bucket)",
            },
            [],
            round((time.perf_counter() - t0) * 1000, 2),
        )


class QuantAgent(BaseAgent):
    agent_id = "QuantAgent"

    def run(self, row: dict[str, Any]) -> AgentResult:
        t0 = time.perf_counter()
        opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        payload = {
            "expected_value": opp.get("expected_value"),
            "expected_return_pct": opp.get("expected_return_pct"),
            "expected_loss_pct": opp.get("expected_loss_pct"),
            "risk_reward": opp.get("risk_reward") or row.get("risk_reward"),
            "volatility_pct": opp.get("volatility_pct"),
            "liquidity_score": scores.get("liquidity"),
            "risk_score": scores.get("risk"),
            "p_win_heuristic": opp.get("p_win"),  # heuristic — not calibrated probability
            "note": "p_win is heuristic confluence — NOT calibrated probability",
        }
        return AgentResult(
            self.agent_id,
            True,
            payload,
            [],
            round((time.perf_counter() - t0) * 1000, 2),
        )


def _dir_from_action(row: dict[str, Any]) -> str:
    a = str(row.get("final_decision") or row.get("decision") or row.get("signal") or "WAIT").upper()
    if a in {"STRONG_BUY", "BUY", "AL"}:
        return "BULLISH"
    if a in {"STRONG_SELL", "SELL", "SAT"}:
        return "BEARISH"
    return "NEUTRAL"
