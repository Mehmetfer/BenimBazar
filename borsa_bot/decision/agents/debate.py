"""DebateEngine — Bull / Bear / Critic cases from structured features only (no LLM MD)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from decision.agents import AgentResult, BaseAgent
from decision.agents.analysts import QuantAgent, TechnicalAgent


@dataclass
class DebateResult:
    bull_case: list[str] = field(default_factory=list)
    bear_case: list[str] = field(default_factory=list)
    critic: list[str] = field(default_factory=list)
    bull_score: float = 0.0
    bear_score: float = 0.0
    bull_beats_bear: bool = False
    confirmation_bias_risk: bool = False
    overconfidence_risk: bool = False
    data_conflict: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BullAgent(BaseAgent):
    agent_id = "BullAgent"

    def run(self, row: dict[str, Any], technical: dict[str, Any], quant: dict[str, Any]) -> AgentResult:
        reasons: list[str] = []
        score = 0.0
        ev = quant.get("expected_value")
        if ev is not None and float(ev) > 0:
            reasons.append(f"POSITIVE_EV={ev}")
            score += min(30.0, float(ev) * 10)
        if technical.get("volume_ok"):
            reasons.append("VOLUME_CONFIRMATION")
            score += 15
        mtf = (technical.get("evidence") or {}).get("mtf") or {}
        vals = {str(v).upper() for v in mtf.values()}
        if any(v in {"BULL", "BULLISH", "BUY", "UP"} for v in vals) and not any(
            v in {"BEAR", "BEARISH", "SELL", "DOWN"} for v in vals
        ):
            reasons.append("MTF_ALIGNED_BULLISH")
            score += 25
        tm = float((technical.get("evidence") or {}).get("trend_momentum") or 0)
        if tm >= 70:
            reasons.append("TREND_MOMENTUM_STRONG")
            score += 20
        if row.get("is_favorite"):
            reasons.append("FAVORITE_PRIORITY_ONLY")  # not a buy reason by itself
            score += 2
        rr = quant.get("risk_reward")
        if rr is not None and float(rr) >= 2.0:
            reasons.append("RISK_REWARD_GE_2")
            score += 10
        if not reasons:
            reasons.append("NO_STRONG_BULL_EVIDENCE")
        return AgentResult(self.agent_id, True, {"reasons": reasons, "score": round(score, 1)}, [])


class BearAgent(BaseAgent):
    agent_id = "BearAgent"

    def run(self, row: dict[str, Any], technical: dict[str, Any], quant: dict[str, Any], regime: dict[str, Any]) -> AgentResult:
        reasons: list[str] = []
        score = 0.0
        ev = quant.get("expected_value")
        if ev is None:
            reasons.append("EV_UNKNOWN")
            score += 15
        elif float(ev) <= 0:
            reasons.append("NEGATIVE_OR_ZERO_EV")
            score += 35
        mtf = (technical.get("evidence") or {}).get("mtf") or {}
        vals = {str(v).upper() for v in mtf.values()}
        buys = any(v in {"BULL", "BULLISH", "BUY", "UP"} for v in vals)
        sells = any(v in {"BEAR", "BEARISH", "SELL", "DOWN"} for v in vals)
        if buys and sells:
            reasons.append("MTF_CONFLICT")
            score += 30
        primary = str((regime or {}).get("primary") or row.get("regime") or "").upper()
        if primary in {"BEAR", "STRONG_BEAR"}:
            reasons.append("BEAR_REGIME")
            score += 25
        if not technical.get("volume_ok"):
            reasons.append("WEAK_VOLUME")
            score += 15
        liq = quant.get("liquidity_score")
        if liq is not None and float(liq) < 40:
            reasons.append("LOW_LIQUIDITY")
            score += 20
        spread = row.get("spread_pct")
        if spread is not None and float(spread) > 1.0:
            reasons.append("HIGH_SPREAD")
            score += 15
        reasons.append("BREAKOUT_FAILURE_RISK")
        score += 8
        return AgentResult(self.agent_id, True, {"reasons": reasons, "score": round(min(100.0, score), 1)}, [])


class CriticAgent(BaseAgent):
    agent_id = "CriticAgent"

    def run(self, bull: dict[str, Any], bear: dict[str, Any], technical: dict[str, Any], quant: dict[str, Any]) -> AgentResult:
        notes: list[str] = []
        conf_bias = False
        overconf = False
        conflict = "MTF_CONFLICT" in (bear.get("reasons") or [])
        if conflict:
            notes.append("Both sides underweight higher-TF conflict risk" if not any(
                "MTF" in r for r in (bull.get("reasons") or [])
            ) else "MTF conflict acknowledged — edge may be short-term only")
        if float(bull.get("score") or 0) > 70 and float(quant.get("expected_value") or 0) < 0.5:
            notes.append("Bull score high while EV thin — overconfidence risk")
            overconf = True
        if "FAVORITE_PRIORITY_ONLY" in (bull.get("reasons") or []) and len(bull.get("reasons") or []) <= 2:
            notes.append("Favorite bias without setup depth — confirmation bias risk")
            conf_bias = True
        if not bull.get("reasons") or bull.get("reasons") == ["NO_STRONG_BULL_EVIDENCE"]:
            notes.append("Bull case empty — should default WAIT/NO_TRADE")
        if "BREAKOUT_FAILURE_RISK" in (bear.get("reasons") or []):
            notes.append("Bear flags breakout failure — require volume follow-through")
        if not notes:
            notes.append("No major missing critique — still not a guarantee")
        return AgentResult(
            self.agent_id,
            True,
            {
                "notes": notes,
                "confirmation_bias_risk": conf_bias,
                "overconfidence_risk": overconf,
                "data_conflict": conflict,
            },
            notes,
        )


class DebateEngine(BaseAgent):
    agent_id = "DebateEngine"

    def __init__(self) -> None:
        self.technical = TechnicalAgent()
        self.quant = QuantAgent()
        self.bull = BullAgent()
        self.bear = BearAgent()
        self.critic = CriticAgent()

    def run(self, row: dict[str, Any], *, regime: dict[str, Any] | None = None) -> AgentResult:
        t0 = time.perf_counter()
        tech = self.technical.run(row).payload
        quant = self.quant.run(row).payload
        bull = self.bull.run(row, tech, quant).payload
        bear = self.bear.run(row, tech, quant, regime or {}).payload
        critic = self.critic.run(bull, bear, tech, quant).payload
        debate = DebateResult(
            bull_case=list(bull.get("reasons") or []),
            bear_case=list(bear.get("reasons") or []),
            critic=list(critic.get("notes") or []),
            bull_score=float(bull.get("score") or 0),
            bear_score=float(bear.get("score") or 0),
            bull_beats_bear=float(bull.get("score") or 0) > float(bear.get("score") or 0) + 5,
            confirmation_bias_risk=bool(critic.get("confirmation_bias_risk")),
            overconfidence_risk=bool(critic.get("overconfidence_risk")),
            data_conflict=bool(critic.get("data_conflict")),
        )
        return AgentResult(
            self.agent_id,
            True,
            {
                "debate": debate.to_dict(),
                "technical": tech,
                "quant": quant,
            },
            [],
            round((time.perf_counter() - t0) * 1000, 2),
        )
