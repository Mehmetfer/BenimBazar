"""Paper-trading decision feedback loop (never LIVE).

Wires CalibrationMonitor + post_trade lessons + strategy ranking into the
paper decision engine so losing strategies shrink / retire and confidence
haircuts actually update.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.calibration import CalibrationMonitor
from analytics.post_trade import DriftAlert, PostTradeReview, detect_model_drift, review_closed_trade
from strategy.ranking import StrategyPerf, rank_strategies


@dataclass
class StrategyStats:
    name: str
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    gross_win: float = 0.0
    gross_loss: float = 0.0  # absolute losses

    @property
    def hit_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def expectancy(self) -> float:
        return self.total_pnl / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss <= 1e-9:
            return 9.9 if self.gross_win > 0 else 0.0
        return self.gross_win / self.gross_loss

    @property
    def retired(self) -> bool:
        """Continuously losing strategy after enough paper samples."""
        if self.trades < 5:
            return False
        if self.hit_rate <= 0.35 and self.expectancy < 0:
            return True
        if self.trades >= 8 and self.expectancy < -50:
            return True
        if self.trades >= 6 and self.profit_factor < 0.6 and self.hit_rate < 0.4:
            return True
        return False


@dataclass
class PaperDecisionFeedback:
    """Paper-only evaluation → risk reduction / NO-TRADE advice."""

    calibration: CalibrationMonitor = field(default_factory=CalibrationMonitor)
    strategies: dict[str, StrategyStats] = field(default_factory=dict)
    lessons: list[PostTradeReview] = field(default_factory=list)
    recent_outcomes: list[bool] = field(default_factory=list)
    recent_ev_proxy: list[float] = field(default_factory=list)
    drift: DriftAlert = field(default_factory=lambda: DriftAlert(False, "stable"))
    max_lessons: int = 50

    def on_closed_trade(
        self,
        *,
        symbol: str,
        pnl: float,
        entry_reason: str,
        regime_at_entry: str,
        regime_at_exit: str,
        stop_distance_pct: float,
        confidence: float,
        strategy: str,
        news_flag: str | None = None,
    ) -> PostTradeReview:
        review = review_closed_trade(
            symbol=symbol,
            pnl=pnl,
            entry_reason=entry_reason,
            regime_at_entry=regime_at_entry,
            regime_at_exit=regime_at_exit,
            stop_distance_pct=stop_distance_pct,
            news_flag=news_flag,
        )
        self.lessons.append(review)
        if len(self.lessons) > self.max_lessons:
            self.lessons = self.lessons[-self.max_lessons :]

        self.calibration.record(float(confidence), review.won)

        name = (strategy or "ensemble").strip() or "ensemble"
        st = self.strategies.setdefault(name, StrategyStats(name=name))
        st.trades += 1
        st.total_pnl += float(pnl)
        if review.won:
            st.wins += 1
            st.gross_win += float(pnl)
        else:
            st.gross_loss += abs(float(pnl))

        self.recent_outcomes.append(review.won)
        self.recent_ev_proxy.append(float(pnl))
        self.recent_outcomes = self.recent_outcomes[-30:]
        self.recent_ev_proxy = self.recent_ev_proxy[-30:]
        self._refresh_drift()
        return review

    def _refresh_drift(self) -> None:
        if len(self.recent_outcomes) < 8:
            self.drift = DriftAlert(False, "insufficient_sample")
            return
        hit = sum(1 for x in self.recent_outcomes if x) / len(self.recent_outcomes)
        avg_ev = sum(self.recent_ev_proxy) / len(self.recent_ev_proxy)
        # Baseline ~0.50 heuristic for paper confluence; decay → DEFENSIVE
        self.drift = detect_model_drift(
            recent_hit_rate=hit,
            baseline_hit_rate=0.50,
            recent_avg_ev=avg_ev,
        )

    def is_strategy_retired(self, strategy: str) -> bool:
        st = self.strategies.get((strategy or "ensemble").strip() or "ensemble")
        return bool(st and st.retired)

    def size_multiplier_for(self, strategy: str) -> float:
        """1.0 normal · 0.5 underperform · 0.0 retired (NO-TRADE path)."""
        st = self.strategies.get((strategy or "ensemble").strip() or "ensemble")
        if not st or st.trades < 3:
            return 1.0
        if st.retired:
            return 0.0
        if st.hit_rate < 0.45 and st.expectancy < 0:
            return 0.5
        if st.profit_factor < 0.85 and st.trades >= 4:
            return 0.65
        return 1.0

    def should_force_defensive(self) -> bool:
        return bool(self.drift.defensive)

    def adjust_confidence(self, confidence: float) -> float:
        return self.calibration.adjust(confidence)

    def ranking_report(self) -> list[dict]:
        """Risk-adjusted ranking from paper outcomes (not illustrative samples)."""
        perfs: list[StrategyPerf] = []
        for st in self.strategies.values():
            if st.trades < 1:
                continue
            # Proxy DD: losing streak impact as |min cumulative|/starting-ish
            dd = 0.0
            if st.gross_loss > 0:
                dd = min(80.0, abs(st.gross_loss) / max(abs(st.total_pnl) + st.gross_loss, 1.0) * 40)
            sharpe = (st.expectancy / max(1.0, abs(st.expectancy) + 1)) * (st.hit_rate * 2)
            perfs.append(
                StrategyPerf(
                    name=st.name,
                    net_return=round(st.total_pnl / 100.0, 2),
                    max_drawdown=round(dd, 2),
                    sharpe=round(sharpe, 3),
                    sortino=round(sharpe * 1.1, 3),
                    calmar=round(st.expectancy / max(dd, 0.1), 3),
                    profit_factor=round(st.profit_factor, 3),
                    expectancy=round(st.expectancy, 2),
                )
            )
        ranked = rank_strategies(perfs)
        out = []
        for i, s in enumerate(ranked):
            st = self.strategies[s.name]
            out.append(
                {
                    "rank": i + 1,
                    "name": s.name,
                    "trades": st.trades,
                    "hit_rate": round(st.hit_rate, 3),
                    "expectancy": round(st.expectancy, 2),
                    "profit_factor": round(st.profit_factor, 3),
                    "retired": st.retired,
                    "size_mult": self.size_multiplier_for(s.name),
                    "risk_adjusted_score": s.risk_adjusted_score,
                    "source": "paper_feedback",
                }
            )
        return out

    def report(self) -> dict:
        return {
            "calibration": self.calibration.report(),
            "drift": {"defensive": self.drift.defensive, "reason": self.drift.reason},
            "strategies": self.ranking_report(),
            "lessons": [
                {"symbol": x.symbol, "pnl": x.pnl, "won": x.won, "lessons": x.lessons}
                for x in self.lessons[-10:]
            ],
            "note": "Paper evaluation only — does not enable LIVE trading.",
        }
