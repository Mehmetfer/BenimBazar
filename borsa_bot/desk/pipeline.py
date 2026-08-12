"""Final decision pipeline — each stage PASS / FAIL / UNKNOWN."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from decision.quality import score_decision_quality
from desk.consensus import ConsensusResult, compute_consensus
from desk.entry import EntryPlan, evaluate_entry
from desk.models import PipelineStageResult, StageStatus
from desk.committee import MasterTradingCommittee
from desk.thesis import build_thesis
from profit.costs import edge_covers_cost


def _stage(name: str, ok: bool | None, msg: str, **details: Any) -> PipelineStageResult:
    if ok is None:
        status = StageStatus.UNKNOWN
    elif ok:
        status = StageStatus.PASS
    else:
        status = StageStatus.FAIL
    return PipelineStageResult(stage=name, status=status, message=msg, details=details)


class FinalDecisionPipeline:
    """DATA QUALITY → … → RISK APPROVAL → EXECUTION → CONSENSUS."""

    def __init__(self) -> None:
        self.committee = MasterTradingCommittee()

    def run(
        self,
        row: dict[str, Any],
        *,
        trading: Any | None = None,
        context: dict[str, Any] | None = None,
        portfolio: dict[str, Any] | None = None,
        debate: dict[str, Any] | None = None,
        regime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        portfolio = portfolio or {}
        regime = regime or {"primary": str(row.get("regime") or "UNKNOWN")}
        stages: list[PipelineStageResult] = []
        critical_unknown = False

        # 1 DATA QUALITY
        data_valid = bool(context.get("data_valid"))
        data_fresh = bool(context.get("data_fresh", True))
        kind = str(context.get("data_kind") or row.get("data_source_kind") or "UNKNOWN").upper()
        if not data_valid:
            stages.append(_stage("DATA_QUALITY", False, "data_invalid"))
        elif not data_fresh:
            stages.append(_stage("DATA_QUALITY", False, "data_stale"))
        else:
            stages.append(_stage("DATA_QUALITY", True, f"ok kind={kind}", data_kind=kind))

        # 2 MARKET REGIME
        primary = str(regime.get("primary") or "UNKNOWN").upper()
        if primary in {"UNKNOWN", "UNCERTAIN", ""}:
            stages.append(_stage("MARKET_REGIME", None, "regime_unknown"))
            critical_unknown = True
        else:
            stages.append(_stage("MARKET_REGIME", True, primary, regime=primary))

        # 3 MARKET CONTEXT
        index_ok = context.get("index_bullish")
        if index_ok is None:
            stages.append(_stage("MARKET_CONTEXT", None, "index_trend_unknown"))
        else:
            stages.append(_stage("MARKET_CONTEXT", True, f"index_bullish={index_ok}"))

        # 4 STRATEGY SELECTION
        votes_raw = row.get("strategy_votes") if isinstance(row.get("strategy_votes"), dict) else {}
        stages.append(
            _stage(
                "STRATEGY_SELECTION",
                bool(votes_raw) or bool(row.get("final_decision")),
                f"strategies={len(votes_raw)}",
                votes=votes_raw,
            )
        )

        # 5 SIGNAL
        signal = str(row.get("final_decision") or row.get("decision") or "WAIT").upper()
        sig_ok = signal in {"BUY", "STRONG_BUY", "AL", "SELL", "SAT"}
        stages.append(_stage("SIGNAL", sig_ok, signal))

        # 6 EXPECTED VALUE
        opp = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        ev = opp.get("expected_value")
        if ev is None:
            stages.append(_stage("EXPECTED_VALUE", None, "ev_unknown"))
            critical_unknown = True
        elif float(ev) <= 0 or not edge_covers_cost(float(ev)):
            stages.append(_stage("EXPECTED_VALUE", False, f"net_ev={ev}", cost_floor=settings.min_expected_value))
        else:
            stages.append(_stage("EXPECTED_VALUE", True, f"net_ev={ev}"))

        # 7 LIQUIDITY
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        liq = scores.get("liquidity")
        if liq is None:
            stages.append(_stage("LIQUIDITY", None, "liquidity_unknown"))
        elif float(liq) < 35:
            stages.append(_stage("LIQUIDITY", False, f"liquidity={liq}"))
        else:
            stages.append(_stage("LIQUIDITY", True, f"liquidity={liq}"))

        # 8 EXECUTION COST
        spread = row.get("spread_pct")
        if spread is not None and float(spread) > 1.5:
            stages.append(_stage("EXECUTION_COST", False, f"spread={spread}%"))
        elif spread is None:
            stages.append(_stage("EXECUTION_COST", None, "spread_unknown"))
        else:
            stages.append(_stage("EXECUTION_COST", True, f"spread={spread}"))

        # 9 PORTFOLIO FIT
        open_pos = int(portfolio.get("open_positions") or 0)
        max_pos = int(portfolio.get("max_open_positions") or settings.max_open_positions)
        pf_ok = open_pos < max_pos
        stages.append(_stage("PORTFOLIO_FIT", pf_ok, f"open={open_pos}/{max_pos}"))

        # 10 COMMITTEE + CONSENSUS
        analyst_votes = self.committee.evaluate(row, trading=trading, context=context, portfolio=portfolio)
        consensus: ConsensusResult = compute_consensus(analyst_votes, regime=primary)
        stages.append(
            _stage(
                "COMMITTEE_CONSENSUS",
                consensus.decision == "BUY" and not consensus.veto,
                consensus.decision,
                veto=consensus.veto,
                disagreement=consensus.disagreement,
            )
        )

        # Quality score
        quality = score_decision_quality(row=row, context=context, debate=debate, regime=regime)

        # Entry plan
        entry: EntryPlan = evaluate_entry(
            price=float(row.get("price") or 0),
            bid=row.get("bid"),
            ask=row.get("ask"),
            spread_pct=spread,
            liquidity_score=float(liq) if liq is not None else None,
            signal_decision=signal,
            consensus_decision=consensus.decision,
        )

        # Final decision
        final = "NO_TRADE"
        if critical_unknown:
            final = "NO_TRADE"
        elif consensus.veto:
            final = "NO_TRADE"
        elif any(s.status == StageStatus.FAIL for s in stages[:9]):
            final = "NO_TRADE"
        elif consensus.decision == "BUY" and entry.action == "BUY" and quality.total >= 55:
            final = "BUY"
        elif consensus.decision == "BUY" and entry.action == "WAIT":
            final = "WAIT"
        elif consensus.decision == "SELL":
            final = "SELL"

        thesis = build_thesis(row, analyst_votes, consensus_decision=consensus.decision, confidence=consensus.confidence)

        return {
            "final_decision": final,
            "consensus": consensus.to_dict(),
            "stages": [s.to_dict() for s in stages],
            "signal_quality": quality.total,
            "quality": quality.to_dict(),
            "entry": entry.to_dict(),
            "thesis": thesis.to_dict(),
            "committee_votes": [v.to_dict() for v in analyst_votes],
            "critical_unknown": critical_unknown,
        }
