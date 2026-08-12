"""Master Trading Committee — independent analyst evaluations."""

from __future__ import annotations

from typing import Any

from autonomous.governors import evaluate_governors
from config.settings import settings
from decision.agents.analysts import QuantAgent, TechnicalAgent
from decision.agents.regime import RegimeAgent
from desk.models import AnalystRole, AnalystVote
from fundamental.provider import get_fundamentals, score_fundamentals
from profit.costs import edge_covers_cost, round_trip_cost_pct
from technical.sector import liquidity_score


def _dir_from_row(row: dict[str, Any]) -> str:
    a = str(row.get("final_decision") or row.get("decision") or row.get("signal") or "WAIT").upper()
    if a in {"STRONG_BUY", "BUY", "AL"}:
        return "BUY"
    if a in {"STRONG_SELL", "SELL", "SAT"}:
        return "SELL"
    return "NO_TRADE"


class MasterTradingCommittee:
    """Eight specialist roles — each produces decision, confidence, reason, risk."""

    def __init__(self) -> None:
        self.technical = TechnicalAgent()
        self.quant = QuantAgent()
        self.regime = RegimeAgent()

    def evaluate(
        self,
        row: dict[str, Any],
        *,
        trading: Any | None = None,
        context: dict[str, Any] | None = None,
        portfolio: dict[str, Any] | None = None,
    ) -> list[AnalystVote]:
        context = context or {}
        portfolio = portfolio or {}
        votes: list[AnalystVote] = []

        tech_r = self.technical.run(row)
        quant_r = self.quant.run(row)
        tech = tech_r.payload
        quant = quant_r.payload

        regime: dict[str, Any] = {}
        if trading is not None:
            regime = (self.regime.run(trading, context=context).payload or {}).get("regime") or {}
        else:
            regime = {"primary": str(row.get("regime") or "UNKNOWN")}

        primary_regime = str(regime.get("primary") or row.get("regime") or "UNKNOWN").upper()
        opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        ev = opp.get("expected_value")
        liq = scores.get("liquidity")
        spread = row.get("spread_pct")

        # Market analyst — index/sector/breadth from context
        index_bull = bool(context.get("index_bullish"))
        mkt_dec = "BUY" if index_bull and primary_regime in {"BULL", "STRONG_BULL"} else (
            "NO_TRADE" if primary_regime in {"BEAR", "STRONG_BEAR"} else "WAIT"
        )
        votes.append(
            AnalystVote(
                analyst=AnalystRole.MARKET.value,
                decision=mkt_dec,
                confidence=0.72 if context.get("data_valid") else 0.35,
                reason=f"index_bullish={index_bull} regime={primary_regime}",
                risk="market_headwind" if mkt_dec == "NO_TRADE" else "",
                data_quality="KNOWN" if context.get("data_valid") else "UNKNOWN",
            )
        )

        # Quant analyst
        q_dec = "NO_TRADE"
        q_conf = 0.4
        if ev is not None:
            net_ev = float(ev)
            if net_ev > float(settings.min_expected_value) and net_ev > 0:
                q_dec = "BUY"
                q_conf = min(0.92, 0.55 + net_ev * 5)
            else:
                q_dec = "NO_TRADE"
                q_conf = 0.7
        votes.append(
            AnalystVote(
                analyst=AnalystRole.QUANT.value,
                decision=q_dec,
                confidence=q_conf,
                reason=f"net_ev={ev} rr={quant.get('risk_reward')}",
                risk="edge_below_cost" if q_dec == "NO_TRADE" and ev is not None else "",
                expected_edge=float(ev) if ev is not None else None,
            )
        )

        # Technical analyst
        tm = float((tech.get("evidence") or {}).get("trend_momentum") or 0)
        t_dec = _dir_from_row(row) if tm >= 55 else "NO_TRADE"
        votes.append(
            AnalystVote(
                analyst=AnalystRole.TECHNICAL.value,
                decision=t_dec,
                confidence=min(0.9, tm / 100.0) if tm else 0.4,
                reason=f"trend_momentum={tm} volume_ok={tech.get('volume_ok')}",
                risk="mtf_conflict" if row.get("conflict") else "",
            )
        )

        # Fundamental analyst — only when data marked available
        sym = str(row.get("symbol") or "")
        fund_snap = get_fundamentals(sym)
        if fund_snap.available:
            fund_sc, fund_notes = score_fundamentals(fund_snap)
            f_dec = "BUY" if fund_sc >= 60 else ("NO_TRADE" if fund_sc < 45 else "WAIT")
            votes.append(
                AnalystVote(
                    analyst=AnalystRole.FUNDAMENTAL.value,
                    decision=f_dec,
                    confidence=fund_sc / 100.0,
                    reason=",".join(fund_notes[:3]) or "fundamental_scored",
                    risk="synthetic_fundamentals" if getattr(settings, "data_provider", "") == "simulated" else "",
                    data_quality="KNOWN",
                )
            )
        else:
            votes.append(
                AnalystVote(
                    analyst=AnalystRole.FUNDAMENTAL.value,
                    decision="NO_TRADE",
                    confidence=0.0,
                    reason="fundamental_data_unavailable",
                    risk="",
                    data_quality="UNAVAILABLE",
                )
            )

        # Regime analyst
        r_conf = float(regime.get("confidence") or 0.5)
        r_dec = "BUY" if primary_regime in {"BULL", "STRONG_BULL"} else (
            "SELL" if primary_regime in {"BEAR", "STRONG_BEAR"} else "WAIT"
        )
        if primary_regime in {"UNKNOWN", "UNCERTAIN", ""}:
            r_dec = "NO_TRADE"
            r_conf = 0.2
        votes.append(
            AnalystVote(
                analyst=AnalystRole.REGIME.value,
                decision=r_dec,
                confidence=r_conf,
                reason=f"regime={primary_regime} vol={regime.get('volatility', 'n/a')}",
                risk="regime_uncertain" if r_dec == "NO_TRADE" else "",
            )
        )

        # Risk manager — veto authority
        daily_loss = float(portfolio.get("daily_loss_pct") or 0)
        drawdown = float(portfolio.get("drawdown_pct") or 0)
        gov = evaluate_governors(
            daily_loss_pct=daily_loss,
            drawdown_pct=drawdown,
            kill_switch=bool(getattr(settings, "kill_switch", False)),
        )
        risk_dec = "APPROVE"
        risk_conf = 0.8
        risk_reason = gov.reason
        if not gov.new_trades_allowed:
            risk_dec = "VETO"
            risk_conf = 0.95
        elif ev is not None and not edge_covers_cost(float(ev)):
            risk_dec = "VETO"
            risk_conf = 0.88
            risk_reason = f"edge_below_cost net_ev={ev} cost={round_trip_cost_pct():.4f}%"
        votes.append(
            AnalystVote(
                analyst=AnalystRole.RISK.value,
                decision=risk_dec,
                confidence=risk_conf,
                reason=risk_reason,
                risk=gov.state.value,
            )
        )

        # Portfolio manager
        open_pos = int(portfolio.get("open_positions") or 0)
        max_pos = int(portfolio.get("max_open_positions") or settings.max_open_positions)
        exposure = float(portfolio.get("exposure_pct") or 0)
        pf_dec = "APPROVE"
        if open_pos >= max_pos:
            pf_dec = "NO_TRADE"
        elif exposure > 85:
            pf_dec = "WAIT"
        votes.append(
            AnalystVote(
                analyst=AnalystRole.PORTFOLIO.value,
                decision=pf_dec,
                confidence=0.75,
                reason=f"open={open_pos}/{max_pos} exposure={exposure:.1f}%",
                risk="concentration" if exposure > 70 else "",
            )
        )

        # Execution manager — microstructure
        exec_dec = "GO"
        exec_conf = 0.7
        exec_risk = ""
        if liq is not None and float(liq) < 40:
            exec_dec = "NO_TRADE"
            exec_conf = 0.85
            exec_risk = "low_liquidity"
        elif spread is not None and float(spread) > 1.0:
            exec_dec = "WAIT"
            exec_conf = 0.75
            exec_risk = "high_spread"
        votes.append(
            AnalystVote(
                analyst=AnalystRole.EXECUTION.value,
                decision=exec_dec,
                confidence=exec_conf,
                reason=f"liquidity={liq} spread={spread}",
                risk=exec_risk,
            )
        )

        return votes
