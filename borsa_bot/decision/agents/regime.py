"""RegimeAgent — richer regime labels with confidence (wraps detect_regime + overlays)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from decision.agents import AgentResult, BaseAgent
from market_regime.engine import detect_regime


@dataclass
class RegimeSnapshot:
    primary: str
    labels: list[str]
    confidence: float
    volatility: str
    risk_mode: str
    transition: bool
    note: str = "Regime labels are heuristic overlays on detect_regime — not ML"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RegimeAgent(BaseAgent):
    agent_id = "RegimeAgent"

    def run(self, trading: Any, *, context: dict[str, Any] | None = None) -> AgentResult:
        t0 = time.perf_counter()
        context = context or {}
        labels: list[str] = []
        try:
            primary_enum = detect_regime(trading.provider)
            primary = primary_enum.value if hasattr(primary_enum, "value") else str(primary_enum)
        except Exception as exc:  # noqa: BLE001
            snap = RegimeSnapshot(
                primary="UNKNOWN",
                labels=["UNKNOWN"],
                confidence=0.0,
                volatility="UNKNOWN",
                risk_mode="UNKNOWN",
                transition=True,
                note=f"REGIME_ERROR:{exc}",
            )
            return AgentResult(self.agent_id, False, {"regime": snap.to_dict()}, [snap.note], 0.0)

        labels.append(primary)
        # Map existing MarketRegime into extended vocabulary
        if primary in {"STRONG_BULL", "BULL"}:
            labels.extend(["RISK_ON", "ACCUMULATION" if primary == "BULL" else "BREAKOUT"])
            risk_mode = "RISK_ON"
        elif primary in {"STRONG_BEAR", "BEAR"}:
            labels.extend(["RISK_OFF", "DISTRIBUTION" if primary == "BEAR" else "BREAKDOWN"])
            risk_mode = "RISK_OFF"
        else:
            labels.append("SIDEWAYS")
            risk_mode = "NEUTRAL"

        # Volatility overlay from drawdown / context hints (no invented prices)
        dd = float(context.get("drawdown_pct") or 0)
        vol = "HIGH_VOLATILITY" if dd >= 5.0 else ("LOW_VOLATILITY" if dd < 1.5 else "NORMAL_VOLATILITY")
        labels.append(vol)

        transition = primary in {"NEUTRAL"} or "UNKNOWN" in labels
        if transition:
            labels.append("TRANSITION")

        conf = 0.55
        if primary in {"STRONG_BULL", "STRONG_BEAR"}:
            conf = 0.78
        elif primary in {"BULL", "BEAR"}:
            conf = 0.68
        elif primary == "NEUTRAL":
            conf = 0.5
        if not context.get("data_fresh", True):
            conf *= 0.7
            labels.append("UNKNOWN")

        # unique preserve order
        uniq: list[str] = []
        for x in labels:
            if x not in uniq:
                uniq.append(x)

        snap = RegimeSnapshot(
            primary=primary,
            labels=uniq,
            confidence=round(conf, 3),
            volatility=vol,
            risk_mode=risk_mode,
            transition=transition,
        )
        return AgentResult(
            self.agent_id,
            True,
            {"regime": snap.to_dict()},
            [],
            round((time.perf_counter() - t0) * 1000, 2),
        )
