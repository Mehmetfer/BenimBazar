"""Autonomous cycle orchestrator — wraps existing TradingService; paper-only.

AUTO mode = automated PAPER trading. LIVE broker remains locked.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4
import logging

from autonomous.audit import AutonomyAuditLog, make_idempotency_key
from autonomous.discovery import discover_bist, discover_crypto
from autonomous.explain import explain_decision
from autonomous.fast_filter import FastFilterResult, fast_filter_bist
from autonomous.mode_store import AutonomyModeStore, mode_store
from autonomous.modes import UserTradingMode, analysis_allowed, auto_paper_allowed, parse_user_mode
from autonomous.scheduler import CycleSchedulerGuard, scheduler_guard
from config.models import SignalAction, utc_now
from config.settings import settings
from strategy.service import TradingService

logger = logging.getLogger(__name__)
ENTRY_DECISIONS = {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}


@dataclass
class AutonomyCycleReport:
    cycle_id: str
    market: str
    mode: str
    started_at: str
    finished_at: str = ""
    status: str = "RUNNING"
    discovery: dict[str, Any] = field(default_factory=dict)
    filter_stats: dict[str, Any] = field(default_factory=dict)
    deep_count: int = 0
    signals: dict[str, int] = field(default_factory=dict)
    paper_orders: int = 0
    skipped: list[str] = field(default_factory=list)
    explainable: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    live_broker: str = "DISABLED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousAgent:
    """Orchestrates discovery → filter → deep scan → gated paper execution."""

    def __init__(
        self,
        trading: Optional[TradingService] = None,
        audit: Optional[AutonomyAuditLog] = None,
        scheduler: Optional[CycleSchedulerGuard] = None,
    ) -> None:
        self.trading = trading or TradingService()
        self.audit = audit or AutonomyAuditLog()
        self.scheduler = scheduler or scheduler_guard
        self.mode_store: AutonomyModeStore = mode_store
        self._last_report: Optional[AutonomyCycleReport] = None

    def user_mode(self) -> UserTradingMode:
        return self.mode_store.get()

    def set_user_mode(self, mode: str) -> dict[str, Any]:
        m = self.mode_store.set(mode)
        return {
            "ok": True,
            "user_trading_mode": m.value,
            "auto_paper_allowed": auto_paper_allowed(m),
            "live_broker": "DISABLED",
            "note": "AUTO = automated paper only. LIVE broker remains DISABLED.",
        }

    def last_report(self) -> Optional[dict[str, Any]]:
        return self._last_report.to_dict() if self._last_report else None

    def status(self) -> dict[str, Any]:
        mode = self.user_mode()
        return {
            "user_trading_mode": mode.value,
            "auto_paper_allowed": auto_paper_allowed(mode),
            "analysis_allowed": analysis_allowed(mode),
            "live_broker": "DISABLED",
            "live_trading": False,
            "kill_switch": bool(settings.kill_switch)
            or self.trading.capital_mode.value == "KILL_SWITCH",
            "scheduler": self.scheduler.status(),
            "last_cycle": self.last_report(),
            "autonomy_enabled": bool(getattr(settings, "autonomy_enabled", True)),
            "note": "AUTO = automated paper only. LIVE broker is Phase 7 locked.",
        }

    def run_bist_cycle(self, force: bool = False) -> dict[str, Any]:
        return self._run_cycle(market="BIST", force=force)

    def run_crypto_cycle(self, force: bool = False) -> dict[str, Any]:
        if not bool(getattr(settings, "crypto_enabled", False)):
            return {
                "status": "SKIPPED",
                "reason": "CRYPTO_ENABLED=false",
                "live_broker": "DISABLED",
                "market": "CRYPTO",
            }
        return self._run_cycle(market="CRYPTO", force=force)

    def _kill_switch_active(self) -> bool:
        return bool(settings.kill_switch) or self.trading.capital_mode.value == "KILL_SWITCH"

    def _run_cycle(self, market: str, force: bool = False) -> dict[str, Any]:
        mode = self.user_mode()
        cycle_id = f"CYC-{uuid4().hex[:12]}"
        started = utc_now().isoformat()
        report = AutonomyCycleReport(
            cycle_id=cycle_id,
            market=market,
            mode=mode.value,
            started_at=started,
        )

        if mode is UserTradingMode.PAUSED and not force:
            report.status = "PAUSED"
            report.skipped.append("user_mode=PAUSED")
            report.finished_at = utc_now().isoformat()
            self._finish(report, kill_switch=self._kill_switch_active())
            return report.to_dict()

        if not analysis_allowed(mode) and not force:
            report.status = "MODE_BLOCKS_ANALYSIS"
            report.skipped.append(f"mode={mode.value}")
            report.finished_at = utc_now().isoformat()
            self._finish(report, kill_switch=self._kill_switch_active())
            return report.to_dict()

        ok_sched, sched_reason = self.scheduler.try_begin(
            market,
            min_interval_sec=float(getattr(settings, "autonomy_scan_cooldown_seconds", 25.0)),
            force=force,
        )
        if not ok_sched:
            report.status = "SKIPPED_DUPLICATE_SCAN"
            report.skipped.append(sched_reason)
            report.finished_at = utc_now().isoformat()
            self._finish(report, kill_switch=self._kill_switch_active(), note=sched_reason)
            return report.to_dict()

        try:
            if settings.is_live:
                report.status = "BLOCKED_LIVE_MODE"
                report.skipped.append("LIVE_BROKER_LOCKED — autonomy is paper-only")
                report.finished_at = utc_now().isoformat()
                self._finish(report, kill_switch=True, note="live_blocked")
                return report.to_dict()

            if self._kill_switch_active():
                report.status = "KILL_SWITCH_ACTIVE"
                report.skipped.append("kill_switch")
                report.finished_at = utc_now().isoformat()
                self._finish(report, kill_switch=True)
                return report.to_dict()

            if market == "BIST":
                return self._run_bist(report, mode)
            return self._run_crypto(report, mode)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Autonomy cycle failed: %s", exc)
            report.status = "ERROR"
            report.error = str(exc)
            report.finished_at = utc_now().isoformat()
            self._finish(report, kill_switch=self._kill_switch_active(), note=str(exc))
            return report.to_dict()
        finally:
            self.scheduler.end(market)

    def _run_bist(self, report: AutonomyCycleReport, mode: UserTradingMode) -> dict[str, Any]:
        provider_syms = self.trading.provider.list_symbols()
        discovered = discover_bist(provider_symbols=provider_syms)
        favs = self.trading.favorites.symbols(market_type="BIST")
        filt = fast_filter_bist(
            discovered,
            self.trading.provider,
            favorites=favs,
            max_deep=int(getattr(settings, "autonomy_deep_max", 40)),
        )
        report.discovery = {
            "universe": len(discovered),
            "with_market_data": filt.with_market_data,
            "without_market_data": len(discovered) - filt.with_market_data,
            "notes": [
                "BIST100 catalog discovery; deep path only for symbols with provider MD",
                "No fabricated prices for catalog-only symbols",
            ],
        }
        report.filter_stats = {
            "UNIVERSE": filt.universe,
            "WITH_MARKET_DATA": filt.with_market_data,
            "FAST_FILTER": filt.fast_filter,
            "DEEP_ANALYSIS": len(filt.candidates),
            **filt.stats,
        }
        logger.info(
            "AUTONOMY BIST %s | UNIVERSE=%s FAST_FILTER=%s DEEP=%s",
            report.cycle_id,
            filt.universe,
            filt.fast_filter,
            len(filt.candidates),
        )
        self.audit.write_cycle(
            cycle_id=report.cycle_id,
            market="BIST",
            mode=mode.value,
            kill_switch=False,
            filter_info=report.filter_stats,
            summary={"discovery": report.discovery},
            note="cycle_start",
        )

        decisions = self.trading.scan(symbols=filt.candidates or None)
        report.deep_count = len(decisions)
        signal_counts: dict[str, int] = {}

        for d in decisions:
            sig = d.decision.value if d.decision else d.signal.value
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
            ser = self.trading._serialize(d)
            card = explain_decision(ser)
            report.explainable.append(card)
            self.audit.write_symbol_event(
                report.cycle_id,
                "BIST",
                {
                    "symbol": d.symbol,
                    "data_source": getattr(d, "data_source_kind", None),
                    "data_quality": "OK" if getattr(d, "tradeable", False) or d.data_source_kind else "UNKNOWN",
                    "regime": d.regime.value if d.regime else None,
                    "model_score": d.buy_score,
                    "signal": sig,
                    "risk_result": d.risk_verdict or d.risk.value,
                    "trade_plan": ser.get("ai_trade_plan") or ser.get("trade_plan"),
                    "execution_result": None,
                    "prediction_id": None,
                    "explain": card,
                    "payload": {
                        "final_decision": d.final_decision,
                        "ai_confidence": d.ai_confidence,
                        "gate_tradeable": bool(getattr(d, "tradeable", False)),
                    },
                },
            )
            if d.decision in ENTRY_DECISIONS or d.signal == SignalAction.AL:
                if self._maybe_paper_execute(report, d, mode, ser):
                    report.paper_orders += 1

        report.signals = signal_counts
        report.filter_stats["SIGNALS"] = sum(signal_counts.values())
        report.status = "OK"
        report.finished_at = utc_now().isoformat()
        self._finish(report, kill_switch=False)
        return report.to_dict()

    def _run_crypto(self, report: AutonomyCycleReport, mode: UserTradingMode) -> dict[str, Any]:
        """Crypto plane isolated — never calls BIST TradingService execution."""
        from crypto.service import CryptoFoundationService

        if not bool(getattr(settings, "crypto_signals_enabled", False)):
            report.status = "CRYPTO_SIGNALS_DISABLED"
            report.skipped.append("crypto_signals_enabled=false")
            report.finished_at = utc_now().isoformat()
            self._finish(report, kill_switch=False)
            return report.to_dict()

        crypto = CryptoFoundationService()
        crypto.bind_shared(favorites=self.trading.favorites, alerts=self.trading.alerts)
        provider_syms = list(crypto.provider.list_symbols()) if settings.crypto_enabled else []
        discovered = discover_crypto(provider_symbols=provider_syms)
        deep_max = int(getattr(settings, "autonomy_deep_max", 40))
        candidates = [d.symbol for d in discovered if d.has_market_data][:deep_max]
        filt = FastFilterResult(
            universe=len(discovered),
            with_market_data=len(candidates),
            fast_filter=len(candidates),
            candidates=candidates,
            stats={"note": "crypto plane; isolated from BIST"},
        )
        report.discovery = {
            "universe": filt.universe,
            "with_market_data": filt.with_market_data,
            "without_market_data": 0,
        }
        report.filter_stats = {
            "UNIVERSE": filt.universe,
            "FAST_FILTER": filt.fast_filter,
            "DEEP_ANALYSIS": len(candidates),
        }
        self.audit.write_cycle(
            cycle_id=report.cycle_id,
            market="CRYPTO",
            mode=mode.value,
            kill_switch=False,
            filter_info=report.filter_stats,
            summary={"discovery": report.discovery},
            note="cycle_start",
        )

        rows = crypto.scan(symbols=candidates or None)
        report.deep_count = len(rows)
        counts: dict[str, int] = {}
        for row in rows:
            sig = str(row.get("signal") or row.get("decision") or "WAIT")
            counts[sig] = counts.get(sig, 0) + 1
            card = explain_decision(row)
            card["market"] = "CRYPTO"
            report.explainable.append(card)
            self.audit.write_symbol_event(
                report.cycle_id,
                "CRYPTO",
                {
                    "symbol": row.get("symbol"),
                    "data_source": row.get("data_source_kind"),
                    "data_quality": row.get("data_quality") or row.get("freshness"),
                    "regime": row.get("regime"),
                    "model_score": row.get("score") or row.get("confidence"),
                    "signal": sig,
                    "risk_result": row.get("risk_verdict") or row.get("risk"),
                    "trade_plan": row.get("trade_plan"),
                    "explain": card,
                    "payload": row,
                },
            )
            # Auto paper for crypto only when explicitly enabled — never live
            if (
                auto_paper_allowed(mode)
                and sig.upper() in {"BUY", "STRONG_BUY", "AL"}
                and bool(getattr(settings, "crypto_paper_trading_enabled", False))
            ):
                report.skipped.append(f"crypto_auto_paper_not_wired:{row.get('symbol')}")

        report.signals = counts
        report.status = "OK"
        report.finished_at = utc_now().isoformat()
        self._finish(report, kill_switch=False)
        return report.to_dict()

    def _maybe_paper_execute(
        self,
        report: AutonomyCycleReport,
        decision: Any,
        mode: UserTradingMode,
        ser: dict[str, Any],
    ) -> bool:
        if not auto_paper_allowed(mode):
            return False

        plan = decision.ai_trade_plan or decision.trade_plan
        stop = decision.stop_price
        target = decision.target_price
        if plan is None and (stop is None or target is None):
            self.audit.write_symbol_event(
                report.cycle_id,
                "BIST",
                {
                    "symbol": decision.symbol,
                    "signal": decision.decision.value,
                    "execution_result": "NO_TRADE:missing_trade_plan",
                    "payload": {"action": "NO_TRADE", "reason": "missing_trade_plan"},
                },
            )
            return False

        if decision.risk_verdict and str(decision.risk_verdict).upper() in {"REJECT", "BLOCKED"}:
            self.audit.write_symbol_event(
                report.cycle_id,
                "BIST",
                {
                    "symbol": decision.symbol,
                    "signal": decision.decision.value,
                    "risk_result": decision.risk_verdict,
                    "execution_result": "NO_TRADE:risk",
                },
            )
            return False

        if decision.final_decision and str(decision.final_decision).upper() in {
            "NO_TRADE",
            "WAIT",
            "WATCH",
            "ALMA",
            "BEKLE",
        }:
            return False

        if self.trading.ledger.get_position(decision.symbol) is not None:
            self.audit.write_symbol_event(
                report.cycle_id,
                "BIST",
                {
                    "symbol": decision.symbol,
                    "execution_result": "NO_TRADE:position_already_open",
                },
            )
            return False

        sig_name = decision.decision.value if decision.decision else decision.signal.value
        window = int(getattr(settings, "autonomy_idempotency_minutes", 15))
        idem = make_idempotency_key("BIST", decision.symbol, sig_name, window_minutes=window)
        if not self.audit.claim_order_key(idem, decision.symbol, sig_name):
            self.audit.write_symbol_event(
                report.cycle_id,
                "BIST",
                {
                    "symbol": decision.symbol,
                    "execution_result": "NO_TRADE:duplicate_idempotency",
                    "payload": {"key": idem},
                },
            )
            return False

        # Autonomous paper path: approved=True bypasses manual gate only in AUTO mode
        result = self.trading.execute_signal(decision.symbol, approved=True)
        ok = bool(result.get("ok"))
        self.audit.write_symbol_event(
            report.cycle_id,
            "BIST",
            {
                "symbol": decision.symbol,
                "signal": sig_name,
                "trade_plan": ser.get("ai_trade_plan") or ser.get("trade_plan"),
                "execution_result": "PAPER_ORDER" if ok else f"FAILED:{result.get('message') or result.get('reason')}",
                "payload": {
                    k: result.get(k)
                    for k in ("ok", "message", "order_id", "qty", "price", "needs_approval")
                    if k in result
                },
            },
        )
        return ok

    def _finish(
        self,
        report: AutonomyCycleReport,
        *,
        kill_switch: bool,
        note: str = "",
    ) -> None:
        summary = {
            "status": report.status,
            "signals": report.signals,
            "paper_orders": report.paper_orders,
            "deep_count": report.deep_count,
            "skipped": report.skipped,
            "error": report.error,
            "live_broker": "DISABLED",
            "filter": report.filter_stats,
            "discovery": report.discovery,
        }
        # Prefer update if cycle row exists; otherwise insert once
        existing = None
        try:
            existing = self.audit.recent_cycles(limit=50)
            existing = next((c for c in existing if c.get("cycle_id") == report.cycle_id), None)
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            self.audit.update_cycle_summary(
                report.cycle_id,
                summary,
                note=note or report.status,
                kill_switch=kill_switch,
            )
        else:
            self.audit.write_cycle(
                cycle_id=report.cycle_id,
                market=report.market,
                mode=report.mode,
                kill_switch=kill_switch,
                filter_info=report.filter_stats,
                summary=summary,
                note=note or report.status,
            )
        self._last_report = report


_agent: Optional[AutonomousAgent] = None


def get_autonomous_agent(trading: Optional[TradingService] = None) -> AutonomousAgent:
    global _agent
    if _agent is None:
        _agent = AutonomousAgent(trading=trading)
    elif trading is not None and _agent.trading is not trading:
        _agent.trading = trading
    return _agent
