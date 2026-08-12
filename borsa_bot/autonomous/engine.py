"""AutonomousTradingEngine — central production orchestration loop.

Wraps existing TradingService layers. SIGNAL ≠ ORDER.
Gates: DATA → SIGNAL → TRADE_PLAN → RISK → POSITION → EXECUTION → BROKER.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import uuid4

from alerts.bridge import emit_kill_switch, emit_risk_alert
from autonomous.audit import AutonomyAuditLog
from autonomous.desk_gate import evaluate_desk_gate
from autonomous.discovery import discover_bist
from autonomous.events import AutonomyEventLog, AutonomyEventType
from autonomous.execution_modes import ExecutionMode, parse_execution_mode
from autonomous.explain import explain_decision
from autonomous.fast_filter import fast_filter_bist
from autonomous.gates import evaluate_pretrade_gates
from autonomous.governors import evaluate_governors
from autonomous.health import HealthCheckResult, run_health_check
from autonomous.levels import resolve_autonomy_level
from autonomous.mode_store import AutonomyModeStore, mode_store
from autonomous.modes import UserTradingMode, analysis_allowed, auto_paper_allowed
from autonomous.monitor import monitor_and_exit
from autonomous.orders import OrderState, make_client_order_id, order_record
from autonomous.rate_limit import order_rate_limiter
from autonomous.reason_codes import ReasonCode, explain_packet, reasons_from_gate
from autonomous.reconcile import reconcile_live, reconcile_paper
from autonomous.recovery import attempt_provider_recover
from autonomous.scheduler import CycleSchedulerGuard, scheduler_guard
from autonomous.self_awareness import self_awareness as build_self_awareness
from config.models import OrderRequest, SignalAction, utc_now
from config.settings import settings
from decision.engine import AIDecisionEngine
from execution.broker_adapter import ExecutionRouter, LiveBrokerDisabled
from strategy.service import TradingService

logger = logging.getLogger(__name__)
ENTRY = {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}


@dataclass
class EngineCycleReport:
    cycle_id: str
    market: str
    user_mode: str
    execution_mode: str
    started_at: str
    finished_at: str = ""
    status: str = "RUNNING"
    health: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    filter_stats: dict[str, Any] = field(default_factory=dict)
    symbols_scanned: int = 0
    signals_generated: int = 0
    signals: dict[str, int] = field(default_factory=dict)
    ranked: list[dict[str, Any]] = field(default_factory=list)
    shadow_intents: list[dict[str, Any]] = field(default_factory=list)
    orders_submitted: int = 0
    orders: list[dict[str, Any]] = field(default_factory=list)
    exits: list[dict[str, Any]] = field(default_factory=list)
    reconcile: dict[str, Any] = field(default_factory=dict)
    explainable: list[dict[str, Any]] = field(default_factory=list)
    ai_decision: dict[str, Any] = field(default_factory=dict)
    desk_gate: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    live_broker: str = "DISABLED"
    note: str = "SIGNAL ≠ ORDER · DESK gate on AUTO · LIVE default locked"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousTradingEngine:
    """Production-grade autonomous loop coordinator (fail-closed)."""

    def __init__(
        self,
        trading: Optional[TradingService] = None,
        *,
        audit: Optional[AutonomyAuditLog] = None,
        events: Optional[AutonomyEventLog] = None,
        scheduler: Optional[CycleSchedulerGuard] = None,
        modes: Optional[AutonomyModeStore] = None,
        router: Optional[ExecutionRouter] = None,
    ) -> None:
        self.trading = trading or TradingService()
        self.audit = audit or AutonomyAuditLog()
        self.events = events or AutonomyEventLog()
        self.scheduler = scheduler or scheduler_guard
        self.modes = modes or mode_store
        self.router = router or ExecutionRouter(paper=self.trading.broker, live=LiveBrokerDisabled())
        self.ai = AIDecisionEngine(self.trading)
        self._last: Optional[EngineCycleReport] = None
        self._halted: bool = False
        self._halt_reason: str = ""

    # --- mode accessors ---
    def user_mode(self) -> UserTradingMode:
        return self.modes.get()

    def execution_mode(self) -> ExecutionMode:
        return self.modes.get_execution_mode()

    def set_execution_mode(self, mode: str) -> dict[str, Any]:
        m = self.modes.set_execution_mode(mode)
        return {
            "ok": True,
            "execution_mode": m.value,
            "live_broker_enabled": bool(getattr(settings, "live_broker_enabled", False)),
            "note": "LIVE requires LIVE_BROKER_ENABLED + real adapter; default PAPER",
        }

    def status(self) -> dict[str, Any]:
        um = self.user_mode()
        em = self.execution_mode()
        health = run_health_check(self.trading, execution_mode=em.value)
        blocked = self._halted or health.blocked
        level = resolve_autonomy_level(um, em, blocked=blocked)
        gov = evaluate_governors(
            daily_loss_pct=float(self.trading.ledger.daily_loss_pct()),
            drawdown_pct=float(self.trading.ledger.drawdown_pct()),
            kill_switch=bool(settings.kill_switch),
        )
        if not gov.new_trades_allowed:
            blocked = True
        live_flag = bool(getattr(settings, "live_broker_enabled", False))
        return {
            "autonomous_mode": bool(getattr(settings, "autonomy_enabled", True)) and not self._halted,
            "autonomy_level": level.to_dict(),
            "autonomous_status": "BLOCKED" if blocked else "ACTIVE",
            "blocked_reason": self._halt_reason or (None if gov.new_trades_allowed else gov.reason),
            "governor": gov.to_dict(),
            "user_trading_mode": um.value,
            "execution_mode": em.value,
            "blocked": blocked,
            "halt_reason": self._halt_reason,
            "halted": self._halted,
            "health": health.to_dict(),
            "live_broker": "DISABLED" if not live_flag else "ENABLED_FLAG_ONLY",
            "live_trading": False,
            "desk_gate_auto": bool(getattr(settings, "desk_gate_auto", True)),
            "honesty": {
                "trading_maturity_level": level.level,
                "trading_maturity_label": level.label,
                "full_level8_claimed": False,
                "live_ready": False,
                "live_exec_selected_but_locked": em is ExecutionMode.LIVE and not live_flag,
                "desk_gate_auto": bool(getattr(settings, "desk_gate_auto", True)),
                "signal_ne_order": True,
                "note": "Trading L* ≠ protocol Otonomi L8 · AI score ≠ profit",
            },
            "account": {
                "equity": self.trading.ledger.equity(),
                "cash": self.trading.ledger.cash,
                "daily_pnl": self.trading.ledger.daily_pnl(),
                "open_positions": self.trading.ledger.open_position_count(),
            },
            "last_cycle": self._last.to_dict() if self._last else None,
            "ai": self.ai.status(),
            "note": self._last.note if self._last else "AUTONOMOUS ENGINE ready · DESK gate · LIVE locked",
        }

    def self_awareness(self) -> dict[str, Any]:
        return build_self_awareness(self.trading, self)

    def halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        self.events.emit(AutonomyEventType.KILL_SWITCH, payload={"reason": reason})
        try:
            emit_kill_switch(self.trading.alerts)
        except Exception:  # noqa: BLE001
            pass

    def clear_halt(self) -> None:
        """Manual clear only — never auto-clears financial ambiguity."""
        self._halted = False
        self._halt_reason = ""

    def run_cycle(self, market: str = "BIST", *, force: bool = False) -> dict[str, Any]:
        if not bool(getattr(settings, "autonomy_enabled", True)):
            return {"status": "AUTONOMOUS_DISABLED", "live_broker": "DISABLED"}
        if market.upper() != "BIST":
            return {"status": "MARKET_NOT_SUPPORTED_IN_ENGINE", "market": market, "hint": "use crypto plane separately"}

        um = self.user_mode()
        em = self.execution_mode()
        cycle_id = f"ATE-{uuid4().hex[:12]}"
        report = EngineCycleReport(
            cycle_id=cycle_id,
            market="BIST",
            user_mode=um.value,
            execution_mode=em.value,
            started_at=utc_now().isoformat(),
            live_broker="DISABLED" if not getattr(settings, "live_broker_enabled", False) else "FLAG_ON_ADAPTER_PENDING",
        )

        if self._halted and not force:
            report.status = "HALTED"
            report.errors.append(self._halt_reason or "HALTED")
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        if um is UserTradingMode.PAUSED and not force:
            report.status = "PAUSED"
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        if not analysis_allowed(um) and not force:
            report.status = "MODE_BLOCKS_ANALYSIS"
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        ok_s, reason_s = self.scheduler.try_begin(
            "BIST",
            min_interval_sec=float(getattr(settings, "autonomy_scan_cooldown_seconds", 25.0)),
            force=force,
        )
        if not ok_s:
            report.status = "SKIPPED_DUPLICATE_SCAN"
            report.errors.append(reason_s)
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        try:
            return self._run_bist(report, um, em)
        except Exception as exc:  # noqa: BLE001
            logger.exception("engine cycle failed: %s", exc)
            report.status = "ERROR"
            report.errors.append(str(exc))
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()
        finally:
            self.scheduler.end("BIST")

    def _run_bist(
        self,
        report: EngineCycleReport,
        um: UserTradingMode,
        em: ExecutionMode,
    ) -> dict[str, Any]:
        self.events.emit(AutonomyEventType.SCAN_STARTED, cycle_id=report.cycle_id, market="BIST")

        # 1) HEALTH CHECK
        health = run_health_check(self.trading, execution_mode=em.value)
        report.health = health.to_dict()
        if health.blocked:
            report.status = "BLOCKED"
            report.errors.extend(health.failures)
            self.events.emit(
                AutonomyEventType.HEALTH_FAIL,
                cycle_id=report.cycle_id,
                market="BIST",
                payload=health.to_dict(),
            )
            self.events.emit(AutonomyEventType.CYCLE_BLOCKED, cycle_id=report.cycle_id, payload={"failures": health.failures})
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        # Transient recover attempt if warned stale
        if any("STALE" in w for w in health.warnings):
            rec = attempt_provider_recover(self.trading)
            if not rec.get("ok"):
                report.errors.append("RECOVERY_FAILED")

        # 2) LOAD ACCOUNT / POSITIONS (implicit via ledger)
        # 3) DISCOVERY + FAST FILTER (full catalog; deep only with MD — no fabricated prices)
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
            "note": "Scanner uses BIST100 catalog ∩ provider MD; no hardcoded 3-symbol demo list",
        }
        report.filter_stats = {
            "UNIVERSE": filt.universe,
            "FULL_MARKET_UNIVERSE": filt.universe,
            "WITH_MARKET_DATA": filt.with_market_data,
            "ACTIVE_TRADEABLE_WITH_MD": filt.with_market_data,
            "FAST_FILTER": filt.fast_filter,
            "QUALIFIED": filt.fast_filter,
            "DEEP_ANALYSIS": len(filt.candidates),
            "ANALYZED": len(filt.candidates),
            "TOP_DISPLAY": min(10, len(filt.candidates)),
            "note": "UI top list ≠ full universe. Catalog may be 500+; MD subset is provider-limited.",
            **filt.stats,
        }

        # 4) SCAN / ANALYZE (existing TradingService — single canonical signal path)
        decisions = self.trading.scan(symbols=filt.candidates or None)
        report.symbols_scanned = len(decisions)
        signal_counts: dict[str, int] = {}
        ranked_rows: list[dict[str, Any]] = []
        entry_queue: list[tuple[Any, dict[str, Any]]] = []

        for d in decisions:
            sig = d.decision.value if d.decision else d.signal.value
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
            ser = self.trading._serialize(d)
            card = explain_decision(ser)
            report.explainable.append(card)
            self.events.emit(
                AutonomyEventType.SIGNAL_CREATED,
                cycle_id=report.cycle_id,
                market="BIST",
                symbol=d.symbol,
                payload={"signal": sig, "score": d.buy_score, "model_score": d.ai_confidence},
            )
            ranked_rows.append(
                {
                    "symbol": d.symbol,
                    "signal": sig,
                    "final_decision": d.final_decision,
                    "buy_score": d.buy_score,
                    "model_score": d.ai_confidence,
                    "priority_score": ser.get("priority_score"),
                    "is_favorite": ser.get("is_favorite"),
                    "risk_verdict": d.risk_verdict,
                    "data_source_kind": getattr(d, "data_source_kind", None),
                    "tradeable": getattr(d, "tradeable", False),
                }
            )
            # Defer entries until AI Decision Engine has observed/ranked (L7 pipeline order)
            if d.decision in ENTRY or d.signal == SignalAction.AL:
                entry_queue.append((d, ser))

        # Rank: STRONG_BUY → favorites → BUY → … ; demote stale/risk
        def _rank_key(row: dict[str, Any]) -> tuple:
            sig = str(row.get("signal") or "")
            order = {
                "STRONG_BUY": 0,
                "BUY": 2,
                "AL": 2,
                "WAIT": 3,
                "WATCH": 3,
                "BEKLE": 3,
                "SELL": 4,
                "SAT": 4,
                "STRONG_SELL": 5,
                "NO_TRADE": 6,
                "ALMA": 6,
            }.get(sig, 7)
            if row.get("is_favorite") and order in {2, 3}:
                order = 1
            risk_bad = str(row.get("risk_verdict") or "").upper() in {"REJECT", "BLOCKED"}
            stale = str(row.get("data_source_kind") or "").upper() in {"STALE", "UNKNOWN", "MOCK"}
            return (1 if risk_bad or stale else 0, order, -(row.get("priority_score") or row.get("buy_score") or 0))

        ranked_rows.sort(key=_rank_key)
        report.ranked = ranked_rows[:40]
        report.signals = signal_counts
        report.signals_generated = sum(signal_counts.values())

        # 4b) AI Decision Engine BEFORE execution — observe/rank/reason/propose (never bypasses risk)
        ai_blocked = False
        try:
            ser_all = [self.trading._serialize(d) for d in decisions]
            ai_report = self.ai.run_from_scan_rows(
                ser_all,
                market_type="BIST",
                top_n=8,
                cycle_id=report.cycle_id,
            )
            report.ai_decision = ai_report
            gov = (ai_report.get("governor") or {})
            if str(gov.get("verdict") or "").upper() == "BLOCK" or str(ai_report.get("ai_status") or "").upper() == "BLOCKED":
                ai_blocked = True
                report.errors.append("AI_GOVERNOR_BLOCK_NO_NEW_ENTRIES")
            self.events.emit(
                AutonomyEventType.SCAN_COMPLETED,
                cycle_id=report.cycle_id,
                market="BIST",
                payload={"ai_top": (ai_report.get("top_card") or {}).get("symbol"), "ai_status": ai_report.get("ai_status")},
            )
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"AI_DECISION:{exc}")
            report.ai_decision = {"status": "ERROR", "error": str(exc), "risk_bypass": False}
            # Fail-closed for AUTO: do not open new entries if AI layer crashed
            if um is UserTradingMode.AUTO:
                ai_blocked = True

        # 4c) Entry candidates → gates → plan → execute/shadow (after AI observation)
        if not ai_blocked:
            for d, ser in entry_queue:
                self._handle_entry_candidate(report, d, ser, um, em)
        else:
            report.errors.append("ENTRIES_SKIPPED_AI_BLOCK")

        self.events.emit(
            AutonomyEventType.SCAN_COMPLETED,
            cycle_id=report.cycle_id,
            market="BIST",
            payload={"symbols_scanned": report.symbols_scanned, "signals": signal_counts},
        )

        # 5) MONITOR / EXIT
        report.exits = monitor_and_exit(self.trading, execution_mode=em.value)

        # 6) RECONCILE
        if em is ExecutionMode.LIVE and getattr(settings, "live_broker_enabled", False):
            rec = reconcile_live(self.trading, self.router.live)
        else:
            rec = reconcile_paper(self.trading)
        report.reconcile = rec.to_dict()
        if rec.halted:
            self.events.emit(AutonomyEventType.RECONCILE_FAIL, cycle_id=report.cycle_id, payload=rec.to_dict())
            self.halt("RECONCILE:" + ",".join(rec.mismatches[:5]))
            report.status = "TRADING_HALTED"
            report.errors.append(self._halt_reason)
            report.finished_at = utc_now().isoformat()
            self._last = report
            return report.to_dict()

        # 7) LEARN — evaluate due predictions only (no self-modifying code)
        try:
            def _px(sym: str) -> float | None:
                try:
                    return float(self.trading.provider.get_quote(sym).price)
                except Exception:  # noqa: BLE001
                    return None

            self.trading.predictions.evaluate_due(_px)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"LEARN:{exc}")

        report.status = "OK"
        report.finished_at = utc_now().isoformat()
        self.audit.write_cycle(
            cycle_id=report.cycle_id,
            market="BIST",
            mode=f"{um.value}/{em.value}",
            kill_switch=settings.kill_switch,
            filter_info=report.filter_stats,
            summary={
                "status": report.status,
                "signals": report.signals,
                "orders_submitted": report.orders_submitted,
                "shadow_intents": len(report.shadow_intents),
                "symbols_scanned": report.symbols_scanned,
                "desk_gate": report.desk_gate.get("stats") or {},
            },
            note=report.status,
        )
        self._last = report
        return report.to_dict()

    def _handle_entry_candidate(
        self,
        report: EngineCycleReport,
        decision: Any,
        ser: dict[str, Any],
        um: UserTradingMode,
        em: ExecutionMode,
    ) -> None:
        gate = evaluate_pretrade_gates(self.trading, decision)
        if not gate.passed:
            codes: list[str] = []
            for g in gate.gates:
                if not g.passed:
                    codes.extend(reasons_from_gate(g.name, g.reason))
            self.events.emit(
                AutonomyEventType.GATE_FAIL,
                cycle_id=report.cycle_id,
                market="BIST",
                symbol=decision.symbol,
                payload={**gate.to_dict(), "reason_codes": codes, "explain": explain_packet(signal=str(decision.decision), reason_codes=codes)},
            )
            self.events.emit(
                AutonomyEventType.RISK_REJECTED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload={"reason": gate.reason, "reason_codes": codes},
            )
            return

        # Governor size cap (never increases risk)
        gov = evaluate_governors(
            daily_loss_pct=float(self.trading.ledger.daily_loss_pct()),
            drawdown_pct=float(self.trading.ledger.drawdown_pct()),
            kill_switch=bool(settings.kill_switch),
        )
        if not gov.new_trades_allowed:
            self.events.emit(
                AutonomyEventType.RISK_REJECTED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload=gov.to_dict(),
            )
            return

        rl = order_rate_limiter.allow_order(decision.symbol)
        if not rl.allowed:
            self.events.emit(
                AutonomyEventType.ORDER_BLOCKED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload={"reason": rl.reason, "reason_codes": [ReasonCode.RATE_LIMIT.value]},
            )
            return

        self.events.emit(
            AutonomyEventType.TRADE_PLAN_CREATED,
            cycle_id=report.cycle_id,
            symbol=decision.symbol,
            payload={
                "stop": decision.stop_price,
                "target": decision.target_price,
                "ai_plan": bool(decision.ai_trade_plan),
                "governor_size_mult": gov.size_mult,
            },
        )
        self.events.emit(
            AutonomyEventType.RISK_APPROVED,
            cycle_id=report.cycle_id,
            symbol=decision.symbol,
            payload={"risk_verdict": decision.risk_verdict},
        )

        # Institutional desk gate — required for AUTO paper fills (fail-closed)
        desk_require = bool(getattr(settings, "desk_gate_auto", True)) and auto_paper_allowed(um) and em is ExecutionMode.PAPER
        desk = evaluate_desk_gate(
            self.trading,
            decision,
            ser if isinstance(ser, dict) else None,
            require_buy=desk_require or em is ExecutionMode.SHADOW,
        )
        stats = report.desk_gate.setdefault(
            "stats",
            {"evaluated": 0, "allowed": 0, "blocked": 0, "veto": 0},
        )
        stats["evaluated"] = int(stats.get("evaluated") or 0) + 1
        if desk.get("veto"):
            stats["veto"] = int(stats.get("veto") or 0) + 1
        if desk.get("allowed"):
            stats["allowed"] = int(stats.get("allowed") or 0) + 1
        else:
            stats["blocked"] = int(stats.get("blocked") or 0) + 1
        report.desk_gate.setdefault("last", desk)
        report.explainable.append(
            {
                "symbol": decision.symbol,
                "desk_decision": desk.get("decision"),
                "desk_entry": desk.get("entry_action"),
                "desk_allowed": desk.get("allowed"),
                "desk_reason": desk.get("reason"),
            }
        )

        if desk_require and not desk.get("allowed"):
            self.events.emit(
                AutonomyEventType.ORDER_BLOCKED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload={
                    "reason": desk.get("reason") or "DESK_GATE",
                    "desk_decision": desk.get("decision"),
                    "desk_entry": desk.get("entry_action"),
                    "veto": desk.get("veto"),
                    "reason_codes": ["DESK_GATE"],
                },
            )
            return

        # PAPER/SEMI user modes: no auto fills. SHADOW may still emit WOULD_* intents.
        if em is ExecutionMode.SHADOW:
            pass  # fall through to shadow intent block
        elif um in {UserTradingMode.PAPER, UserTradingMode.SEMI_AUTO, UserTradingMode.PAUSED}:
            return
        elif not auto_paper_allowed(um):
            return

        # Allow SHADOW intents in SEMI_AUTO and AUTO (and when execution_mode=SHADOW)
        if em is ExecutionMode.SHADOW:
            intent = {
                "would": "BUY",
                "symbol": decision.symbol,
                "entry": decision.price,
                "stop": decision.stop_price,
                "target": decision.target_price,
                "signal": decision.decision.value,
                "model_score": decision.ai_confidence,
                "execution_mode": "SHADOW",
            }
            # size estimate via risk engine without submitting
            try:
                quote = self.trading.provider.get_quote(decision.symbol)
                bars = self.trading.provider.get_bars(decision.symbol, 220)
                from indicators.engine import compute_indicators

                ind = compute_indicators(bars)
                size_mult = (decision.opportunity.position_size_mult if decision.opportunity else 0.5) * gov.size_mult
                rd = self.trading.risk.evaluate_entry(
                    symbol=decision.symbol,
                    sector=quote.sector,
                    price=quote.price,
                    ind=ind,
                    action=SignalAction.AL,
                    plan=decision.trade_plan,
                    spread_pct=quote.spread_pct,
                    correlated_sector_risk=self.trading.ledger.sector_risk_pct(quote.sector),
                    opportunity=decision.opportunity,
                    capital_mode=self.trading.capital_mode,
                    size_mult=size_mult,
                )
                intent["quantity"] = rd.quantity if rd.allowed else 0
                intent["governor_size_mult"] = gov.size_mult
                intent["risk_pct"] = getattr(settings, "max_position_risk_pct", None)
                intent["risk_allowed"] = rd.allowed
                intent["risk_reason"] = rd.reason
            except Exception as exc:  # noqa: BLE001
                intent["quantity"] = None
                intent["error"] = str(exc)
            report.shadow_intents.append(intent)
            self.events.emit(
                AutonomyEventType.SHADOW_INTENT,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload=intent,
            )
            coid = make_client_order_id(
                market="BIST",
                symbol=decision.symbol,
                side="BUY",
                signal=decision.decision.value,
                cycle_id=report.cycle_id,
            )
            report.orders.append(order_record(client_order_id=coid, state=OrderState.SHADOW, symbol=decision.symbol, side="BUY", qty=intent.get("quantity"), price=decision.price, message="WOULD BUY"))
            return

        if em is ExecutionMode.LIVE:
            # Fail-closed unless unlocked
            if not bool(getattr(settings, "live_broker_enabled", False)):
                self.events.emit(
                    AutonomyEventType.ORDER_BLOCKED,
                    cycle_id=report.cycle_id,
                    symbol=decision.symbol,
                    payload={"reason": "LIVE_BROKER_DISABLED"},
                )
                return

        if em is ExecutionMode.PAPER and not auto_paper_allowed(um):
            return

        # PAPER (or unlocked LIVE) submit via router — re-check risk sizing
        quote = self.trading.provider.get_quote(decision.symbol)
        bars = self.trading.provider.get_bars(decision.symbol, 220)
        from indicators.engine import compute_indicators

        ind = compute_indicators(bars)
        size_mult = (decision.opportunity.position_size_mult if decision.opportunity else 0.5) * gov.size_mult
        rd = self.trading.risk.evaluate_entry(
            symbol=decision.symbol,
            sector=quote.sector,
            price=quote.price,
            ind=ind,
            action=SignalAction.AL,
            plan=decision.trade_plan,
            spread_pct=quote.spread_pct,
            correlated_sector_risk=self.trading.ledger.sector_risk_pct(quote.sector),
            opportunity=decision.opportunity,
            capital_mode=self.trading.capital_mode,
            size_mult=size_mult,
        )
        if not rd.allowed:
            self.events.emit(
                AutonomyEventType.RISK_REJECTED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload={"reason": rd.reason},
            )
            return

        coid = make_client_order_id(
            market="BIST",
            symbol=decision.symbol,
            side="BUY",
            signal=decision.decision.value,
            cycle_id=report.cycle_id,
            window_minutes=int(getattr(settings, "autonomy_idempotency_minutes", 15)),
        )
        # Idempotency claim
        if not self.audit.claim_order_key(coid, decision.symbol, decision.decision.value):
            self.events.emit(
                AutonomyEventType.ORDER_BLOCKED,
                cycle_id=report.cycle_id,
                symbol=decision.symbol,
                payload={"reason": "DUPLICATE_CLIENT_ORDER_ID", "client_order_id": coid},
            )
            return

        order = OrderRequest(
            symbol=decision.symbol,
            side="BUY",
            quantity=rd.quantity,
            price=quote.price,
            reason=f"autonomous:{report.cycle_id}:{decision.decision.value}",
            stop_price=rd.stop_price,
            target_price=rd.target_price,
            client_order_id=coid,
        )
        result = self.router.submit(order, quote.sector, execution_mode=em.value)
        report.orders_submitted += 1 if result.ok and result.status != "SHADOW" else 0
        state = OrderState.FILLED if result.ok and result.status == "FILLED" else (
            OrderState.BLOCKED if result.status == "BLOCKED" else (
                OrderState.REJECTED if not result.ok else OrderState.SUBMITTED
            )
        )
        rec = order_record(
            client_order_id=coid,
            state=state,
            symbol=decision.symbol,
            side="BUY",
            qty=result.quantity or rd.quantity,
            price=result.fill_price or quote.price,
            broker_order_id=result.order_id,
            message=result.message,
            extra={"execution_mode": em.value, "pnl_type": "PAPER" if em is ExecutionMode.PAPER else em.value},
        )
        report.orders.append(rec)
        self.events.emit(
            AutonomyEventType.ORDER_SUBMITTED if result.ok else AutonomyEventType.ORDER_BLOCKED,
            cycle_id=report.cycle_id,
            symbol=decision.symbol,
            payload=rec,
        )
        if result.ok and result.status == "FILLED":
            self.events.emit(AutonomyEventType.ORDER_FILLED, cycle_id=report.cycle_id, symbol=decision.symbol, payload=rec)
            self.events.emit(AutonomyEventType.POSITION_OPENED, cycle_id=report.cycle_id, symbol=decision.symbol, payload=rec)


_engine: Optional[AutonomousTradingEngine] = None


def get_autonomous_engine(trading: Optional[TradingService] = None) -> AutonomousTradingEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousTradingEngine(trading=trading)
    elif trading is not None and _engine.trading is not trading:
        _engine.trading = trading
        _engine.router = ExecutionRouter(paper=trading.broker, live=LiveBrokerDisabled())
    return _engine
