from __future__ import annotations

from dataclasses import asdict
from datetime import date

from ai.quality import assess_signal_quality, classify_volatility_regime
from analytics.paper_feedback import PaperDecisionFeedback
from ai.calibration import CalibrationMonitor
from decision.feedback import DecisionFeedbackLoop
from decision.pipeline import F6PaperLoop
from decision.replay import DecisionReplayStore
from alerts import AlertManager
from alerts.bridge import (
    emit_daily_summary,
    emit_execution_exit,
    emit_kill_switch,
    emit_order_lifecycle,
    emit_risk_alert,
    emit_signal_alerts,
)
from alpha.engine import aggregate_alpha, run_alpha_ensemble
from config.models import (
    CapitalMode,
    MarketRegime,
    OrderRequest,
    RiskLevel,
    ScoreBundle,
    SignalAction,
    SymbolDecision,
)
from config.settings import SYSTEM_OBJECTIVES, settings
from data.providers import MarketDataProvider, create_provider
from execution.paper import PaperBroker
from execution.safety import SafetyGate
from factors.engine import compute_factors
from fundamental.provider import get_fundamentals, score_fundamentals
from indicators.engine import compute_indicators
from market_regime.engine import detect_regime, trend_label
from news.analyzer import classify_headline, latest_stub_headline, score_news
from portfolio.construction import build_correlation_matrix, size_position
from portfolio.ledger import PortfolioLedger
from profit.ev import compute_opportunity, decide_matrix, dynamic_size_multiplier
from profit.modes import select_capital_mode
from profit.protection import initial_protect, update_profit_protection
from risk.engine import ENTRY_ACTIONS, EXIT_ACTIONS, RiskEngine
from signals.engine import (
    build_trade_plan,
    detect_conflict,
    market_score,
    momentum_score,
    score_sell,
    technical_score,
    volume_score,
)
from trade_plan.engine import ai_plan_to_dict, build_ai_trade_plan, legacy_from_ai
from strategy.modules import ensemble_votes, regime_weights, weighted_ensemble_bias
from strategy.ranking import example_ranking_report
from technical.mtf import analyze_mtf, mtf_conflict_risk
from technical.price_action import analyze_price_action
from technical.sector import liquidity_score, sector_relative_strength
from universe.engine import select_universe
from engines.orchestrator import MultiHorizonOrchestrator
from favorites import (
    FavoritesStore,
    FavoriteSort,
    check_favorite_price_alerts,
    classify_scanner,
    compute_priority_score,
    display_priority_bucket,
    emit_favorite_signal_alerts,
    run_deeper_analysis,
    sort_rank_key,
)
from prediction import PredictionTrackingService
from dashboard.daily import build_daily_home
from data.integrity import FreshnessStatus, format_age_tr
from config.models import utc_now

def _to_exec_signal(decision: SignalAction) -> SignalAction:
    if decision in {SignalAction.STRONG_BUY, SignalAction.BUY}:
        return SignalAction.AL
    if decision in {SignalAction.STRONG_SELL, SignalAction.SELL}:
        return SignalAction.SAT
    if decision in {SignalAction.NO_TRADE, SignalAction.AVOID}:
        return SignalAction.ALMA
    return SignalAction.BEKLE


class TradingService:
    def __init__(self) -> None:
        self.provider: MarketDataProvider = create_provider(settings.data_provider)
        self.ledger = PortfolioLedger()
        self.risk = RiskEngine(self.ledger)
        self.broker = PaperBroker(self.ledger)
        self.safety = SafetyGate()
        self.alerts = AlertManager()
        self.favorites = FavoritesStore()
        # Prediction tracking MEASURES only — never alters Risk/Execution decisions
        self.predictions = PredictionTrackingService(settings=settings, alert_manager=self.alerts)
        self.system_status = "OK"
        self.last_error = ""
        self.pending_approvals: dict[str, dict] = {}
        self.capital_mode = CapitalMode.NORMAL
        # Paper decision feedback: calibration + post_trade + strategy retirement
        self.calibration = CalibrationMonitor()
        self.paper_feedback = PaperDecisionFeedback(calibration=self.calibration)
        # Night-2 F6 intelligent decision loop (paper/simulation only — LIVE forbidden)
        self.f6_feedback = DecisionFeedbackLoop()
        self.f6_replay = DecisionReplayStore()
        self.f6_loop = F6PaperLoop(
            feedback=self.f6_feedback,
            replay=self.f6_replay,
            strategy="ensemble",
        )
        self.multi = MultiHorizonOrchestrator(
            self.provider, equity=settings.starting_cash, calibration=self.calibration
        )
        self._entry_meta: dict[str, dict] = {}
        self._protect_state: dict[str, object] = {}
        self._last_risk_alert_reason = ""
        self._kill_switch_alerted = False
        self._emit_signal_alerts = True  # dashboard/scan may publish SIGNAL alerts (not fills)
        self._last_favorite_scan_ts = 0.0
        self._favorite_deeper_cache: dict[str, dict] = {}
        self._prediction_cards: dict[str, dict] = {}

    def multi_horizon(self) -> dict:
        self.multi.equity = self.ledger.equity()
        self.multi.provider = self.provider
        return self.multi.run()

    def health(self) -> dict:
        meta = self.provider.source_meta(settings.data_freshness_sec)
        has_data = self.provider.has_market_data()
        fresh = bool(meta.is_live_market or meta.freshness.value == "FRESH_SIMULATED")
        # Safety: simulated is OK for paper; live/required disconnect is not
        data_fresh_for_safety = fresh if has_data else False
        ok, reason = self.safety.evaluate(
            data_fresh=data_fresh_for_safety,
            api_ok=has_data or meta.kind.value == "SIMULATED",
            order_status_ok=True,
            spread_pct=0.0,
            daily_loss_pct=self.ledger.daily_loss_pct(),
            clock_ok=True,
            max_spread_pct=settings.max_spread_pct,
        )
        if meta.kind.value in {"REQUIRED", "UNAVAILABLE"} or not has_data:
            ok, reason = False, "DATA_SOURCE_REQUIRED"
        self.risk.refresh_pause_state()
        if settings.kill_switch or self.capital_mode == CapitalMode.KILL_SWITCH:
            status = "KILL_SWITCH"
        elif self.capital_mode == CapitalMode.CAPITAL_PROTECTION:
            status = "CAPITAL_PROTECTION"
        elif self.risk.paused:
            status = f"PAUSE:{self.risk.pause_reason}"
        elif not ok:
            status = reason
        else:
            status = self.system_status
        live_ok, live_failed = self.risk.preflight_live(
            data_fresh=bool(meta.is_live_market), api_ok=meta.is_live_market, market_open=meta.market_session.value == "OPEN"
        )
        # Never LIVE READY without verified live feed
        live_ready = False
        live_failed = list(live_failed) + ["NO_VERIFIED_LIVE_MARKET_DATA"]
        if not meta.is_live_market:
            live_ok = False
        # Alert layer observes state — never changes decisions
        if settings.kill_switch or self.capital_mode == CapitalMode.KILL_SWITCH:
            if not self._kill_switch_alerted:
                emit_kill_switch(self.alerts)
                self._kill_switch_alerted = True
        else:
            self._kill_switch_alerted = False
        if meta.freshness == FreshnessStatus.STALE or meta.freshness == FreshnessStatus.DISCONNECTED:
            emit_risk_alert(self.alerts, "data feed failure / stale data")
        if not ok and reason in {"STALE_DATA", "ABNORMAL_SPREAD", "BROKER_API_FAILURE", "DATA_FEED_FAILURE", "DATA_SOURCE_REQUIRED"}:
            emit_risk_alert(self.alerts, reason)
        if self.risk.paused and self.risk.pause_reason != self._last_risk_alert_reason:
            detail = {
                "max_drawdown": "Portföy drawdown limiti aşıldı. Yeni işlemler durduruldu.",
                "weekly_loss_limit": "Haftalık zarar limiti aşıldı. Yeni işlemler durduruldu.",
                "daily_loss_limit": "Günlük zarar limiti aşıldı. Yeni işlemler durduruldu.",
            }.get(self.risk.pause_reason, self.risk.pause_reason)
            if "consecutive" in (self.risk.pause_reason or ""):
                detail = f"Ardışık kayıp limiti: {self.risk.pause_reason}"
            emit_risk_alert(self.alerts, detail)
            self._last_risk_alert_reason = self.risk.pause_reason
        return {
            "status": status,
            "mode": settings.mode,
            "capital_mode": self.capital_mode.value,
            "data_fresh": data_fresh_for_safety,
            "kill_switch": settings.kill_switch,
            "paused": self.risk.paused,
            "safety_ok": ok,
            "live_preflight_ok": live_ok,
            "live_preflight_failed": live_failed,
            "live_ready": live_ready,
            "manual_approval": settings.require_manual_approval,
            "error": self.last_error,
            "objectives": SYSTEM_OBJECTIVES,
            "philosophy": (
                "LESS DATA, MORE DECISION. "
                "Sermaye koruma → risk kontrolü → yüksek olasılıklı fırsat. "
                "NO_TRADE birinci sınıf. Uydurma veri yasak. "
                "SİMÜLE ≠ CANLI. TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK. "
                "LIVE READY yalnızca doğrulanmış piyasa + broker ile."
            ),
            "strategy_ranking_example": example_ranking_report(),
            "strategy_ranking_example_note": "DEAD_ILLUSTRATIVE — use paper_decision_feedback.strategies",
            "paper_decision_feedback": self.paper_feedback.report(),
            "f6_decision_loop": {
                "enabled": True,
                "live_trading": False,
                "calibration": self.calibration.report(),
                "feedback": self.f6_feedback.report(),
                "note": "OBSERVE→REGIME→SIGNAL→RISK→DECISION→PAPER→FEEDBACK (no LIVE)",
            },
            "data_source": meta.to_dict(),
            "system_health": {
                "market_data": "CONNECTED" if meta.connected and has_data else "DISCONNECTED",
                "broker": "PAPER" if not settings.is_live else "BLOCKED",
                "ai": "READY" if has_data else "PAUSED",
                "notifications": "CONNECTED",
                "last_update": meta.last_update,
                "last_update_ago": format_age_tr(meta.age_seconds),
                "price_label": meta.price_label,
            },
            "alerts": {
                "unread": len(self.alerts.log.inbox(limit=20, unread_only=True)),
                "sms_on": self.alerts.settings_store.get().sms_on,
                "push_on": self.alerts.settings_store.get().push_on,
            },
        }

    def f6_paper_decide(self, symbol: str, *, requested_size: float = 10.0) -> dict:
        """Run one F6 paper decision cycle (never LIVE broker execution)."""
        cycle = self.f6_loop.run_cycle(
            provider=self.provider,
            ledger=self.ledger,
            symbol=symbol,
            requested_size=requested_size,
        )
        return cycle.to_dict()

    def tick(self) -> None:
        self.provider.tick()

    def scan(self) -> list[SymbolDecision]:
        self.tick()
        # No fabricated scan when live source required / unavailable
        if not self.provider.has_market_data():
            return []
        # Evaluate matured forecasts against current marks (measurement only)
        try:
            def _px(sym: str) -> float | None:
                try:
                    return float(self.provider.get_quote(sym).price)
                except Exception:  # noqa: BLE001
                    return None

            self.predictions.evaluate_due(_px)
        except Exception:  # noqa: BLE001
            pass
        regime = detect_regime(self.provider)
        index_bars = self.provider.get_bars("XU100", 220)
        index_ind = compute_indicators(index_bars)
        index_bullish = bool(index_ind and index_ind.ema21 > index_ind.ema50)
        atr_index_pct = (index_ind.atr14 / index_ind.ema21 * 100) if index_ind and index_ind.ema21 else 2.0
        weights = regime_weights(regime)

        marks = {}
        decisions: list[SymbolDecision] = []
        self.capital_mode = select_capital_mode(
            self.ledger,
            regime=regime,
            atr_index_pct=atr_index_pct,
            liquidity_ok=True,
            force_defensive=self.paper_feedback.should_force_defensive(),
        )
        self.risk.capital_mode = self.capital_mode
        universe_map = {m.symbol: m for m in select_universe(self.provider)}
        # Correlation series for book awareness
        ret_series: dict[str, list[float]] = {}
        for symbol in self.provider.list_symbols():
            bars_c = self.provider.get_bars(symbol, 40)
            closes = [b.close for b in bars_c]
            ret_series[symbol] = [
                closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]
            ]
        corr_matrix = build_correlation_matrix(ret_series)

        # Priority queue: FAVORITES → rest of market (does not skip non-favorites)
        fav_set = self.favorites.symbols()
        all_syms = [s for s in self.provider.list_symbols() if s != "XU100"]
        ordered = [s for s in all_syms if s in fav_set] + [s for s in all_syms if s not in fav_set]

        for symbol in ordered:
            quote = self.provider.get_quote(symbol)
            marks[symbol] = quote.price
            uni = universe_map.get(symbol)
            bars = self.provider.get_bars(symbol, 240)
            ind = compute_indicators(bars)
            if ind is None:
                continue
            owned = self.ledger.get_position(symbol) is not None
            mtf = analyze_mtf(bars, base_tf_minutes=15)
            mtf_conflict, mtf_penalty, mtf_note = mtf_conflict_risk(mtf)
            mtf_aligned = (not mtf_conflict) and sum(1 for v in mtf.values() if v == "BULL") >= 3
            rs, sector_sc, sector_notes = sector_relative_strength(self.provider, symbol, quote.sector)
            xu = self.provider.get_bars("XU100", 40)
            xu_closes = [b.close for b in xu]
            sym_closes = [b.close for b in bars]
            rs_idx = 0.0
            if len(sym_closes) > 20 and len(xu_closes) > 20 and xu_closes[-20]:
                rs_idx = (sym_closes[-1] / sym_closes[-20] - 1) - (xu_closes[-1] / xu_closes[-20] - 1)
            factors = compute_factors(symbol, sym_closes, ind, quote.price, rs_idx)
            pa = analyze_price_action(bars, ind, quote.volume)
            alphas = run_alpha_ensemble(ind, quote.price, quote.volume, factors, regime)
            alpha_bias, alpha_label, alpha_notes = aggregate_alpha(alphas)
            liq, liq_notes = liquidity_score(quote, ind)
            news = classify_headline(symbol, latest_stub_headline(symbol))
            news_sc, news_notes, news_block = score_news(news)
            tech, tech_reasons = technical_score(ind, quote.price)
            # Soft blend CCI/Williams as confirmation only (not independent)
            if ind.cci20 > 100:
                tech = min(100, tech + 2)
            if ind.williams_r < -80:
                tech = min(100, tech + 1)
            fund, fund_notes = score_fundamentals(get_fundamentals(symbol))
            # Prefer factor quality over raw fund stub if available
            fund = round(0.5 * fund + 0.5 * factors.quality, 1)
            mom = round(0.5 * momentum_score(ind) + 0.5 * factors.momentum, 1)
            vol, vol_notes = volume_score(ind, quote.volume)
            mkt = market_score(regime, index_bullish)
            # Preliminary legacy plan for EV; upgraded to AITradePlan after decision
            plan = build_trade_plan(quote.price, ind)
            if plan:
                plan.t1_exit_pct = settings.tp1_exit_pct
                plan.t2_exit_pct = settings.tp2_exit_pct
                plan.t3_exit_pct = settings.tp3_exit_pct
                plan.trail_remainder_pct = settings.trail_exit_pct
            atr_pct = ind.atr14 / quote.price * 100
            vol_regime = classify_volatility_regime(atr_pct)

            ai_conf, ai_notes = assess_signal_quality(
                action=SignalAction.WAIT,
                buy_score=tech,
                sell_score=0,
                ind=ind,
                regime=regime,
                spread_pct=quote.spread_pct,
                conflict=mtf_conflict,
                mtf=mtf,
            )
            ai_conf = self.paper_feedback.adjust_confidence(ai_conf)
            # Night-2: calibration status is evidence for the decision path (not LIVE)
            cal_status = self.calibration.status().value
            if cal_status == "OVERCONFIDENT":
                ai_conf = max(5.0, ai_conf * 0.85)
                ai_notes = f"{ai_notes};calibration={cal_status}" if ai_notes else f"calibration={cal_status}"
            safety = 80 - mtf_penalty
            if news_block:
                safety -= 30
            if plan is None:
                safety -= 20
            if vol_regime == "EXTREME":
                safety -= 25
            if uni and not uni.eligible:
                safety -= 20
            if pa.false_breakout:
                safety -= 15
            if pa.breakout and not pa.volume_confirmed:
                safety -= 10
            bundle = ScoreBundle(
                technical=round(tech, 1),
                fundamental=round(fund, 1),
                market=round(mkt, 1),
                sector=round(sector_sc, 1),
                momentum=round(mom, 1),
                volume=round(vol, 1),
                news=round(news_sc, 1),
                liquidity=round(liq if not uni else min(liq, uni.liquidity_score), 1),
                risk=round(max(0, 100 - safety), 1),
                ai_confidence=round(ai_conf, 1),
                final=0.0,
            )
            votes = ensemble_votes(ind, quote.price, quote.volume)
            bias = weighted_ensemble_bias(votes, weights)
            # Regime-aware factor weights (not simple average)
            if regime in {MarketRegime.STRONG_BULL, MarketRegime.BULL}:
                factor_blend = factors.momentum * 0.35 + factors.quality * 0.2 + factors.growth * 0.2 + factors.value * 0.1 + factors.volatility * 0.15
            elif regime == MarketRegime.NEUTRAL:
                factor_blend = factors.value * 0.25 + factors.quality * 0.25 + factors.volatility * 0.2 + factors.momentum * 0.15 + factors.growth * 0.15
            else:
                factor_blend = factors.quality * 0.35 + factors.volatility * 0.3 + factors.value * 0.2 + factors.momentum * 0.1 + factors.growth * 0.05
            final = (
                bundle.technical * 0.18
                + factor_blend * 0.18
                + bundle.fundamental * 0.08
                + bundle.market * 0.14
                + bundle.sector * 0.10
                + bundle.momentum * 0.08
                + bundle.volume * 0.08
                + bundle.news * 0.04
                + bundle.liquidity * 0.07
                + (100 - bundle.risk) * 0.05
            )
            final = final * 0.88 + ai_conf * 0.08 + max(-4, min(4, alpha_bias * 8))
            final += max(-5, min(5, bias))
            if regime == MarketRegime.STRONG_BEAR:
                final *= 0.75
            elif regime == MarketRegime.BEAR:
                final *= 0.85
            if mtf_conflict:
                final *= 0.8
            if uni and not uni.eligible:
                final *= 0.7
            bundle.final = round(max(0, min(100, final)), 1)

            conflict, conflict_why = detect_conflict(bundle, bundle.risk >= 55)
            if mtf_conflict:
                conflict = True
                conflict_why = conflict_why or mtf_note
            if pa.false_breakout:
                conflict = True
                conflict_why = "false_breakout"

            opp = compute_opportunity(
                scores=bundle,
                plan=plan,
                price=quote.price,
                ind=ind,
                regime=regime,
                conflict=conflict,
                mtf_aligned=mtf_aligned,
                portfolio_dd_pct=self.ledger.drawdown_pct(),
            )
            strategy_key = str(alpha_label or "ensemble")
            strategy_blocked = self.paper_feedback.is_strategy_retired(strategy_key)
            size_mult = 0.0
            if opp:
                size_mult = dynamic_size_multiplier(opp, capital_mode=self.capital_mode, regime=regime)
                size_mult *= self.paper_feedback.size_multiplier_for(strategy_key)
                size_mult = max(0.0, min(1.0, round(size_mult, 3)))
                opp.position_size_mult = size_mult
                if size_mult <= 0:
                    strategy_blocked = True

            sell_pressure = score_sell(ind, quote.price, quote.volume, owned)
            decision = decide_matrix(
                scores=bundle,
                opp=opp,
                owned=owned,
                sell_pressure=sell_pressure,
                conflict=conflict,
                news_block=news_block,
                capital_mode=self.capital_mode,
                regime=regime,
                strategy_blocked=strategy_blocked,
            )
            if uni and not uni.eligible and decision in {SignalAction.BUY, SignalAction.STRONG_BUY}:
                decision = SignalAction.NO_TRADE
            if pa.breakout and not pa.volume_confirmed and decision in {SignalAction.BUY, SignalAction.STRONG_BUY}:
                decision = SignalAction.WATCH
            signal = _to_exec_signal(decision)

            ai_conf, ai_notes = assess_signal_quality(
                action=signal,
                buy_score=bundle.final,
                sell_score=sell_pressure,
                ind=ind,
                regime=regime,
                spread_pct=quote.spread_pct,
                conflict=conflict,
                mtf=mtf,
            )
            # Paper calibration haircut — only after closed trades have recorded outcomes
            ai_conf = self.paper_feedback.adjust_confidence(ai_conf)
            cal_status = self.calibration.status().value
            if cal_status == "OVERCONFIDENT":
                ai_conf = max(5.0, ai_conf * 0.85)
            bundle.ai_confidence = ai_conf
            # Re-gate BUY if confidence fell below threshold after haircut
            if (
                decision in {SignalAction.BUY, SignalAction.STRONG_BUY}
                and ai_conf < settings.min_ai_confidence_to_trade
            ):
                decision = SignalAction.NO_TRADE
                signal = _to_exec_signal(decision)

            reasons = tech_reasons + vol_notes + fund_notes + sector_notes + news_notes + liq_notes
            reasons.append(f"ensemble_bias={bias}")
            reasons.append(f"alpha_bias={alpha_bias}/{alpha_label}")
            reasons.append(f"capital_mode={self.capital_mode.value}")
            reasons.append(f"price_action={pa.pattern}")
            reasons.extend(alpha_notes[:2])
            if strategy_blocked:
                reasons.append(f"strategy_retired_or_zero_size:{strategy_key}")
            if opp:
                reasons.append(f"EV={opp.expected_value:.3f} P(win)={opp.p_win:.2f}")
            risks = []
            if ind.resistance and quote.price > ind.resistance * 0.98:
                risks.append("Resistance nearby")
            if atr_pct > 3:
                risks.append("ATR elevated")
            if conflict:
                risks.append(f"Conflict: {conflict_why}")
            if opp and opp.expected_value <= 0:
                risks.append("Non-positive expected value")
            if uni and uni.pump_dump_flag:
                risks.append("pump_dump_heuristic")
            if mtf_note:
                risks.append(mtf_note)

            stop = plan.stop if plan else None
            target = plan.target1 if plan else None
            risk_level = RiskLevel.LOW
            risk_verdict = ""
            open_syms = [p.symbol for p in self.ledger.positions()]
            corr_book = 0.0
            if open_syms:
                corr_book = max(corr_matrix.get(symbol, {}).get(s, 0.0) for s in open_syms)
            if signal in ENTRY_ACTIONS:
                tgt = None
                if plan and opp:
                    tgt = size_position(
                        equity=self.ledger.equity(),
                        price=quote.price,
                        stop=plan.stop,
                        opp=opp,
                        capital_mode=self.capital_mode,
                        regime=regime,
                        sector_count=self.ledger.sector_position_count(quote.sector),
                        corr_with_book=corr_book,
                    )
                rd = self.risk.evaluate_entry(
                    symbol=symbol,
                    sector=quote.sector,
                    price=quote.price,
                    ind=ind,
                    action=signal,
                    plan=plan,
                    spread_pct=quote.spread_pct,
                    correlated_sector_risk=self.ledger.sector_risk_pct(quote.sector),
                    opportunity=opp,
                    capital_mode=self.capital_mode,
                    size_mult=size_mult,
                )
                risk_level = rd.risk
                risk_verdict = rd.verdict.value
                if not rd.allowed:
                    decision = SignalAction.NO_TRADE if rd.verdict.value == "REJECT" else SignalAction.WAIT
                    signal = _to_exec_signal(decision)
                    reasons.append(f"RiskEngine {rd.verdict.value}: {rd.reason}")
                    stop, target = rd.stop_price, rd.target_price
                else:
                    if tgt and tgt.quantity > 0:
                        rd_qty = min(rd.quantity, tgt.quantity)
                        if plan:
                            plan.quantity = rd_qty
                    elif plan:
                        plan.quantity = rd.quantity
                    if rd.verdict.value == "REDUCE":
                        reasons.append("RiskEngine REDUCE size")

            # AI Trade Plan Engine — plan ≠ order
            pos = self.ledger.get_position(symbol)
            strategy_label = alpha_label or "ensemble"
            if votes:
                strategy_label = f"{strategy_label}/" + ",".join(list(votes.keys())[:2])
            thesis = (
                f"Trend + momentum + hacim + sektör RS; alpha={alpha_label}; "
                f"PA={pa.pattern}; regime={regime.value}"
            )
            ai_plan = build_ai_trade_plan(
                symbol=symbol,
                price=quote.price,
                ind=ind,
                decision=decision.value,
                confidence=bundle.ai_confidence,
                p_win=opp.p_win if opp else 0.5,
                strategy=strategy_label,
                regime=regime,
                capital_mode=self.capital_mode,
                equity=self.ledger.equity(),
                spread_pct=quote.spread_pct,
                liquidity_ok=bool(uni.eligible) if uni else True,
                corr_ok=corr_book < 0.85,
                size_mult=size_mult if size_mult > 0 else (opp.position_size_mult if opp else 0.5),
                thesis=thesis,
                risk_notes=list(risks),
                opp=opp,
                position=pos,
                sell_pressure=sell_pressure,
            )
            if ai_plan is not None:
                legacy = legacy_from_ai(ai_plan)
                if legacy is not None:
                    plan = legacy
                    if settings:
                        plan.t1_exit_pct = settings.tp1_exit_pct
                        plan.t2_exit_pct = settings.tp2_exit_pct
                        plan.t3_exit_pct = settings.tp3_exit_pct
                        plan.trail_remainder_pct = settings.trail_exit_pct
                    stop = plan.stop
                    target = plan.target1
                if not ai_plan.risk_validated and decision in {
                    SignalAction.BUY,
                    SignalAction.STRONG_BUY,
                }:
                    decision = SignalAction.NO_TRADE
                    signal = _to_exec_signal(decision)
                    reasons.append(f"TradePlan validation FAIL: {ai_plan.risk_reject_reason}")
                    risk_verdict = "REJECT"
                if ai_plan.chase_warning and decision in {SignalAction.BUY, SignalAction.STRONG_BUY}:
                    decision = SignalAction.WAIT
                    signal = SignalAction.BEKLE
                    reasons.append("WAIT_FOR_ENTRY: chase risk")
                final_decision_str = ai_plan.final_decision.value
            else:
                final_decision_str = decision.value

            explanation = (
                f"DECISION={decision.value} FINAL={bundle.final:.0f} EV={(opp.expected_value if opp else 0):.3f} "
                f"Pwin={(opp.p_win if opp else 0):.2f} MODE={self.capital_mode.value}; "
                f"reasons={'; '.join(reasons[:6])}; risks={'; '.join(risks) or 'n/a'}"
            )
            if ai_plan:
                explanation += (
                    f" | PLAN entry={ai_plan.entry_zone.low}-{ai_plan.entry_zone.high} "
                    f"SL={ai_plan.stop_loss} T1={ai_plan.target1.price} RR={ai_plan.risk_reward} "
                    f"state={ai_plan.state.value} pref={ai_plan.preferred_plan}"
                )

            d = SymbolDecision(
                symbol=symbol,
                name=quote.name,
                sector=quote.sector,
                price=quote.price,
                trend=trend_label(ind),
                buy_score=bundle.final,
                sell_score=sell_pressure,
                ai_confidence=bundle.ai_confidence,
                risk=risk_level,
                signal=signal,
                regime=regime,
                stop_price=stop,
                target_price=target,
                explanation=explanation,
                scores=bundle,
                trade_plan=plan,
                opportunity=opp,
                capital_mode=self.capital_mode,
                decision=decision,
                reasons=reasons,
                risks=risks,
                indicators={
                    "rsi": round(ind.rsi14, 2),
                    "atr": round(ind.atr14, 2),
                    "adx": round(ind.adx14, 2),
                    "cci": round(ind.cci20, 2),
                    "williams_r": round(ind.williams_r, 2),
                    "ema9": round(ind.ema9, 2),
                    "ema21": round(ind.ema21, 2),
                    "ema50": round(ind.ema50, 2),
                    "ema100": round(ind.ema100, 2),
                    "ema200": round(ind.ema200, 2),
                    "mfi": round(ind.mfi14, 2),
                    "cmf": round(ind.cmf20, 4),
                },
                strategy_votes=votes,
                strategy_weights=weights,
                mtf=mtf,
                conflict=conflict,
                factors=factors.as_dict(),
                alpha_summary={
                    "bias": alpha_bias,
                    "label": alpha_label,
                    "signals": [{"name": a.name, "signal": a.signal, "confidence": a.confidence, "regime_fit": a.regime_fit} for a in alphas],
                },
                price_action={
                    "pattern": pa.pattern,
                    "volume_confirmed": pa.volume_confirmed,
                    "false_breakout": pa.false_breakout,
                    "notes": pa.notes,
                },
                universe_ok=bool(uni.eligible) if uni else True,
                universe_reason=uni.reason if uni else "ok",
                risk_verdict=risk_verdict,
                ai_trade_plan=ai_plan,
                final_decision=final_decision_str,
            )
            # Deeper analysis for favorites only (FAVORITE ≠ BUY boost)
            if symbol in fav_set:
                try:
                    deeper = run_deeper_analysis(
                        symbol=symbol,
                        bars=bars,
                        ind=ind,
                        price=quote.price,
                        volume=quote.volume,
                        sector=quote.sector,
                        provider=self.provider,
                        user_note=(self.favorites.get(symbol).notes if self.favorites.get(symbol) else ""),
                        corr_with_book=corr_book,
                        regime=regime,
                    )
                    self._favorite_deeper_cache[symbol] = deeper.to_dict()
                except Exception:  # noqa: BLE001
                    pass

            # Prediction tracking — record immutable forecast (MEASURES; does not change decision)
            try:
                pred = self.predictions.record_prediction(
                    symbol=symbol,
                    price=quote.price,
                    signal=decision.value,
                    confidence=float(bundle.ai_confidence),
                    probability=float(opp.p_win if opp else max(0.4, bundle.ai_confidence / 100.0)),
                    ind=ind,
                    regime=regime,
                    sector=quote.sector or "",
                    strategy=strategy_label,
                    opp=opp,
                    plan=ai_plan,
                    is_favorite=symbol in fav_set,
                    features_snapshot={
                        "expected_return_pct": round(opp.expected_return_pct, 4) if opp else None,
                        "expected_value": round(opp.expected_value, 4) if opp else None,
                        "false_breakout": bool(pa.false_breakout),
                        "volume_weak": not bool(pa.volume_confirmed),
                        "news_block": bool(news_block),
                        "atr": round(ind.atr14, 4),
                        "rsi": round(ind.rsi14, 2),
                        "structure": getattr(ind, "structure", None),
                        "final_decision": final_decision_str,
                    },
                )
                card = self.predictions.symbol_card(symbol, latest=pred)
                self._prediction_cards[symbol] = card
                setattr(d, "_prediction_card", card)
            except Exception:  # noqa: BLE001 — tracking never breaks scan
                pass

            decisions.append(d)
            self.ledger.log_decision(
                {
                    "symbol": d.symbol,
                    "price": d.price,
                    "signal": d.decision.value,
                    "buy_score": d.buy_score,
                    "sell_score": d.sell_score,
                    "ai_confidence": d.ai_confidence,
                    "risk": d.risk.value,
                    "explanation": d.explanation,
                    "stop_price": d.stop_price,
                    "target_price": d.target_price,
                }
            )
        self.ledger.set_marks(marks)
        # Favorites-aware ranking: FAVORITE + signal buckets, then priority score
        # FAVORITE ≠ automatic BUY — only ordering / visibility
        def _sort_key(x: SymbolDecision):
            fav = x.symbol in fav_set
            rec = self.favorites.get(x.symbol) if fav else None
            pa = x.price_action or {}
            ps = compute_priority_score(
                is_favorite=fav,
                decision=x.decision.value,
                signal=x.signal.value,
                ai_confidence=x.ai_confidence,
                expected_value=x.opportunity.expected_value if x.opportunity else None,
                risk_reward=x.trade_plan.risk_reward if x.trade_plan else None,
                momentum=(x.factors or {}).get("momentum"),
                regime=x.regime,
                watchlist_priority=rec.priority if rec else 50,
                breakout=bool((pa.get("pattern") or "").upper().find("BREAK") >= 0),
            )
            # stash for serialize via explanation side-channel: use dynamic attr
            setattr(x, "_priority_score", ps)
            setattr(x, "_is_favorite", fav)
            bucket = display_priority_bucket(
                {
                    "is_favorite": fav,
                    "decision": x.decision.value,
                    "signal": x.signal.value,
                    "priority_score": ps,
                    "price_action": pa,
                }
            )
            return (bucket, -ps, -x.buy_score)

        decisions.sort(key=_sort_key)
        if self._emit_signal_alerts:
            try:
                emit_signal_alerts(self.alerts, decisions)
                emit_favorite_signal_alerts(
                    self.alerts,
                    self.favorites,
                    decisions,
                    favorite_voice=settings.favorite_voice_alert,
                    forecast_cards=self._prediction_cards,
                    prediction_formatter=self.predictions.format_favorite_forecast_message,
                )
                plans = {d.symbol: d.ai_trade_plan for d in decisions if d.ai_trade_plan}
                check_favorite_price_alerts(self.alerts, self.favorites, marks, plans)
            except Exception:  # noqa: BLE001 — alerts never break scan
                pass
        return decisions

    def dashboard(self) -> dict:
        decisions = self.scan()
        health = self.health()
        sector_exp: dict[str, int] = {}
        for p in self.ledger.positions():
            sector_exp[p.sector] = sector_exp.get(p.sector, 0) + 1

        def bucket(name: str):
            return [self._serialize(d) for d in decisions if d.decision.value == name or d.signal.value == name]

        universe = [self._serialize(d) for d in decisions]
        favorites = [u for u in universe if u.get("is_favorite")]
        favorites_sorted = sorted(favorites, key=lambda x: sort_rank_key(x, FavoriteSort.PRIORITY), reverse=True)
        top_ops = [u for u in universe if u.get("scanner_class") in {"STRONG_OPPORTUNITY", "OPPORTUNITY"}][:8]
        meta = self.provider.source_meta(settings.data_freshness_sec)
        signals_paused = meta.freshness in {
            FreshnessStatus.STALE,
            FreshnessStatus.DISCONNECTED,
            FreshnessStatus.NO_DATA,
        } or not self.provider.has_market_data()
        daily = build_daily_home(
            universe,
            meta,
            signal_ttl_sec=settings.signal_ttl_sec,
            top_n=settings.daily_top_n,
            signals_paused=signals_paused,
        )

        return {
            "health": health,
            "principle": "LESS DATA, MORE DECISION · FAVORITE ≠ BUY · SİMÜLE ≠ CANLI",
            "daily": daily,
            "favorites": favorites_sorted,
            "favorites_summary": [
                {
                    "symbol": f["symbol"],
                    "decision": f.get("final_decision") or f.get("decision"),
                    "confidence": f.get("ai_confidence"),
                    "priority_score": f.get("priority_score"),
                    "badge": "FAVORİ + PORTFÖYDE" if f.get("favorite_portfolio_badge") else "FAVORİ",
                    "ai_reliability_grade": (f.get("ai_reliability") or {}).get("overall_grade"),
                    "gecmis_dogruluk": f.get("gecmis_dogruluk"),
                    "tahmin_olasiligi": f.get("tahmin_olasiligi"),
                    "forecast_bias": f.get("forecast_bias"),
                }
                for f in favorites_sorted[:12]
            ],
            "top_opportunities": top_ops,
            "portfolio": {
                "equity": round(self.ledger.equity(), 2),
                "cash": round(self.ledger.cash, 2),
                "daily_pnl": round(self.ledger.daily_pnl(), 2),
                "total_pnl": round(self.ledger.total_pnl(), 2),
                "drawdown_pct": round(self.ledger.drawdown_pct(), 2),
                "sector_exposure": sector_exp,
                "open_positions": [
                    {
                        "symbol": p.symbol,
                        "sector": p.sector,
                        "quantity": p.quantity,
                        "avg_cost": round(p.avg_cost, 2),
                        "price": self.ledger.mark_prices.get(p.symbol, p.avg_cost),
                        "stop_price": p.stop_price,
                        "target_price": p.target_price,
                        "is_favorite": self.favorites.is_favorite(p.symbol),
                    }
                    for p in self.ledger.positions()
                ],
            },
            "signals": {
                "STRONG_BUY": bucket("STRONG_BUY"),
                "BUY": bucket("BUY") + bucket("AL"),
                "SELL": bucket("SELL") + bucket("SAT"),
                "STRONG_SELL": bucket("STRONG_SELL"),
                "WATCH": bucket("WATCH"),
                "WAIT": bucket("WAIT") + bucket("BEKLE"),
                "NO_TRADE": bucket("NO_TRADE") + bucket("ALMA"),
                "AL": [self._serialize(d) for d in decisions if d.signal == SignalAction.AL],
                "SAT": [self._serialize(d) for d in decisions if d.signal == SignalAction.SAT],
                "BEKLE": [self._serialize(d) for d in decisions if d.signal == SignalAction.BEKLE],
                "ALMA": [self._serialize(d) for d in decisions if d.signal == SignalAction.ALMA],
            },
            "universe": universe,
            "favorite_performance": self.favorites.performance(),
            "data_source": meta.to_dict(),
            "live_ready": False,
        }

    def _serialize(self, d: SymbolDecision) -> dict:
        fav = bool(getattr(d, "_is_favorite", self.favorites.is_favorite(d.symbol)))
        fav_rec = self.favorites.get(d.symbol) if fav else None
        in_portfolio = self.ledger.get_position(d.symbol) is not None
        pos = self.ledger.get_position(d.symbol)
        change_pct = 0.0
        prev_close = None
        quote_ts = None
        try:
            bars = self.provider.get_bars(d.symbol, 3)
            if bars:
                quote_ts = bars[-1].ts.isoformat() if hasattr(bars[-1].ts, "isoformat") else str(bars[-1].ts)
            if len(bars) >= 2 and bars[-2].close:
                prev_close = round(bars[-2].close, 2)
                change_pct = (bars[-1].close / bars[-2].close - 1) * 100
        except Exception:  # noqa: BLE001
            change_pct = 0.0
            prev_close = None
        ps = float(
            getattr(d, "_priority_score", None)
            or compute_priority_score(
                is_favorite=fav,
                decision=d.decision.value,
                signal=d.signal.value,
                ai_confidence=d.ai_confidence,
                expected_value=d.opportunity.expected_value if d.opportunity else None,
                risk_reward=d.trade_plan.risk_reward if d.trade_plan else None,
                momentum=(d.factors or {}).get("momentum"),
                regime=d.regime,
                watchlist_priority=fav_rec.priority if fav_rec else 50,
            )
        )
        chase = bool(d.ai_trade_plan.chase_warning) if d.ai_trade_plan else False
        scan_class = classify_scanner(d.decision.value, d.risk_verdict, ps, chase).value
        base = {
            "symbol": d.symbol,
            "name": d.name,
            "sector": d.sector,
            "price": d.price,
            "prev_close": prev_close,
            "change_pct": round(change_pct, 2),
            "quote_ts": quote_ts,
            "signal_timestamp": utc_now().isoformat(),
            "trend": d.trend,
            "buy_score": d.buy_score,
            "sell_score": d.sell_score,
            "ai_confidence": d.ai_confidence,
            "risk": d.risk.value,
            "signal": d.signal.value,
            "decision": d.decision.value,
            "regime": d.regime.value,
            "capital_mode": d.capital_mode.value,
            "explanation": d.explanation,
            "stop_price": d.stop_price,
            "target_price": d.target_price,
            "reasons": d.reasons,
            "risks": d.risks,
            "mtf": d.mtf,
            "conflict": d.conflict,
            "strategy_votes": d.strategy_votes,
            "strategy_weights": d.strategy_weights,
            "indicators": d.indicators,
            "factors": d.factors,
            "alpha_summary": d.alpha_summary,
            "price_action": d.price_action,
            "universe_ok": d.universe_ok,
            "universe_reason": d.universe_reason,
            "risk_verdict": d.risk_verdict,
            "final_decision": d.final_decision,
            "is_favorite": fav,
            "in_portfolio": in_portfolio,
            "favorite_portfolio_badge": fav and in_portfolio,
            "priority_score": ps,
            "scanner_class": scan_class,
            "user_note": fav_rec.notes if fav_rec else "",
            "strategy_preference": fav_rec.strategy_preference if fav_rec else [],
            "favorite_groups": fav_rec.groups if fav_rec else [],
            "watchlist_priority": fav_rec.priority if fav_rec else None,
            "news_source": "UNAVAILABLE",
            "kap_source": "UNAVAILABLE",
            "fundamental_source": (
                "SYNTHETIC_PAPER" if settings.data_provider == "simulated" else "UNAVAILABLE"
            ),
        }
        if pos:
            mark = self.ledger.mark_prices.get(pos.symbol, pos.avg_cost)
            base["position"] = {
                "quantity": pos.quantity,
                "avg_cost": round(pos.avg_cost, 2),
                "unrealized_pnl": round((mark - pos.avg_cost) * pos.quantity, 2),
                "stop_price": pos.stop_price,
                "target_price": pos.target_price,
            }
        if d.scores:
            base["scores"] = asdict(d.scores)
        if d.trade_plan:
            base["trade_plan"] = asdict(d.trade_plan)
        if d.opportunity:
            base["opportunity"] = asdict(d.opportunity)
        if d.ai_trade_plan is not None:
            base["ai_trade_plan"] = ai_plan_to_dict(d.ai_trade_plan)
        if fav and d.symbol in self._favorite_deeper_cache:
            base["deeper"] = self._favorite_deeper_cache[d.symbol]
        # AI FORECAST + AI RELIABILITY (METRIC 1 vs METRIC 2 kept distinct)
        card = getattr(d, "_prediction_card", None) or self._prediction_cards.get(d.symbol)
        if card is None:
            try:
                card = self.predictions.symbol_card(d.symbol)
            except Exception:  # noqa: BLE001
                card = None
        if card:
            base["ai_forecast"] = card.get("ai_forecast")
            base["ai_reliability"] = card.get("ai_reliability")
            base["forecast_bias"] = card.get("forecast_bias")
            base["forecast_decomposition"] = card.get("decomposition")
            base["prediction_metric_note"] = card.get("principle")
            # Explicit UI labels
            base["tahmin_olasiligi"] = card.get("current_forecast_probability")
            base["gecmis_dogruluk"] = (card.get("ai_reliability") or {}).get("gecmis_dogruluk")
        return base

    def favorites_view(self, sort: str = "PRIORITY", group: str | None = None) -> dict:
        dash = self.dashboard()
        items = list(dash.get("favorites") or [])
        if group:
            items = [x for x in items if group in (x.get("favorite_groups") or [])]
        try:
            sort_e = FavoriteSort(sort.upper())
        except ValueError:
            sort_e = FavoriteSort.PRIORITY
        reverse = sort_e != FavoriteSort.ALPHABETICAL
        items.sort(key=lambda x: sort_rank_key(x, sort_e), reverse=reverse)
        scanner = {
            "STRONG_OPPORTUNITY": [],
            "OPPORTUNITY": [],
            "WAIT": [],
            "RISK": [],
            "NO_TRADE": [],
        }
        for x in items:
            scanner.setdefault(x.get("scanner_class") or "WAIT", []).append(x["symbol"])
        return {
            "favorites": items,
            "sort": sort_e.value,
            "groups": self.favorites.list_groups(),
            "scanner": scanner,
            "performance": self.favorites.performance(),
            "principle": "FAVORITE ≠ BUY · FAVORITE = PRIORITY ANALYSIS",
        }

    def favorite_detail(self, symbol: str) -> dict:
        symbol = symbol.upper()
        decisions = {d.symbol: d for d in self.scan()}
        d = decisions.get(symbol)
        if not d:
            return {"ok": False, "message": "symbol not found"}
        ser = self._serialize(d)
        return {
            "ok": True,
            "detail": ser,
            "timeline": self.favorites.timeline(symbol),
            "prediction_history": self.predictions.history(symbol, limit=30),
            "prediction_timeline": self.predictions.timeline(symbol, limit=40),
            "ai_forecast": ser.get("ai_forecast"),
            "ai_reliability": ser.get("ai_reliability"),
            "price_alerts": [a.__dict__ for a in self.favorites.list_price_alerts(symbol)],
            "is_favorite": self.favorites.is_favorite(symbol),
            "principle": "FAVORITE ≠ BUY · TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK",
        }

    def execute_signal(self, symbol: str, approved: bool = False) -> dict:
        if settings.is_live:
            return {"ok": False, "message": "LIVE mode blocked — paper trading zorunlu"}
        if not self.provider.has_market_data():
            return {
                "ok": False,
                "message": "DATA SOURCE REQUIRED — canlı/paper veri yok, emir yok",
                "auto_trading": False,
            }
        meta = self.provider.source_meta(settings.data_freshness_sec)
        if meta.freshness.value in {"STALE", "DISCONNECTED", "NO_DATA"}:
            return {
                "ok": False,
                "message": "STALE/DISCONNECTED data — auto trading disabled",
                "auto_trading": False,
            }
        if settings.require_manual_approval and not approved:
            decisions = {d.symbol: d for d in self.scan()}
            d = decisions.get(symbol)
            if not d or d.signal not in ENTRY_ACTIONS | EXIT_ACTIONS and d.signal not in {SignalAction.AL, SignalAction.SAT}:
                return {"ok": False, "message": "no actionable signal to approve"}
            if d.signal not in {SignalAction.AL, SignalAction.SAT}:
                return {"ok": False, "message": "no actionable signal to approve"}
            self.pending_approvals[symbol] = self._serialize(d)
            return {
                "ok": False,
                "needs_approval": True,
                "message": "Manuel onay gerekli — paper emir için approved=true gönderin",
                "suggestion": self.pending_approvals[symbol],
            }
        quote = self.provider.get_quote(symbol)
        ok, reason = self.safety.evaluate(
            data_fresh=self.provider.is_fresh(60),
            api_ok=True,
            order_status_ok=True,
            spread_pct=quote.spread_pct,
            daily_loss_pct=self.ledger.daily_loss_pct(),
            clock_ok=True,
            max_spread_pct=settings.max_spread_pct,
        )
        if not ok:
            return {"ok": False, "message": f"safety halt: {reason}"}
        decisions = {d.symbol: d for d in self.scan()}
        d = decisions.get(symbol)
        if not d:
            return {"ok": False, "message": "symbol not found"}
        quote = self.provider.get_quote(symbol)
        if d.signal == SignalAction.AL:
            bars = self.provider.get_bars(symbol, 220)
            ind = compute_indicators(bars)
            size_mult = d.opportunity.position_size_mult if d.opportunity else 0.5
            rd = self.risk.evaluate_entry(
                symbol=symbol,
                sector=quote.sector,
                price=quote.price,
                ind=ind,
                action=d.signal,
                plan=d.trade_plan,
                spread_pct=quote.spread_pct,
                correlated_sector_risk=self.ledger.sector_risk_pct(quote.sector),
                opportunity=d.opportunity,
                capital_mode=self.capital_mode,
                size_mult=size_mult,
            )
            if not rd.allowed:
                return {"ok": False, "message": rd.reason, "risk": rd.risk.value}
            order = OrderRequest(
                symbol=symbol,
                side="BUY",
                quantity=rd.quantity,
                price=quote.price,
                reason=d.explanation,
                stop_price=rd.stop_price,
                target_price=rd.target_price,
            )
            result = self.broker.submit(order, quote.sector)
            self.pending_approvals.pop(symbol, None)
            if result.ok:
                stop = rd.stop_price
                entry = quote.price
                stop_dist = ((entry - stop) / entry * 100) if stop and entry else 0.0
                alpha = d.alpha_summary or {}
                self._entry_meta[symbol] = {
                    "confidence": float(d.ai_confidence),
                    "strategy": str(alpha.get("label") or "ensemble"),
                    "regime": str(d.regime.value if d.regime else "NEUTRAL"),
                    "entry_reason": d.explanation,
                    "stop_distance_pct": stop_dist,
                    "entry": entry,
                    "stop": stop,
                    "target": rd.target_price,
                }
                if stop:
                    self._protect_state[symbol] = initial_protect(entry, float(stop))
            emit_order_lifecycle(
                self.alerts,
                symbol=symbol,
                side="BUY",
                result=result,
                strategy=d.decision.value,
                price=quote.price,
            )
            return {"ok": result.ok, "result": asdict(result), "alert_note": "ORDER event emitted (not BUY_SIGNAL)"}
        if d.signal == SignalAction.SAT:
            rd = self.risk.evaluate_exit(symbol, SignalAction.SELL)
            if not rd.allowed:
                return {"ok": False, "message": rd.reason}
            order = OrderRequest(
                symbol=symbol,
                side="SELL",
                quantity=rd.quantity,
                price=quote.price,
                reason=d.explanation,
            )
            result = self.broker.submit(order, quote.sector)
            self.pending_approvals.pop(symbol, None)
            if result.ok:
                meta = self._entry_meta.get(symbol, {})
                pnl = 0.0
                with self.ledger._connect() as conn:
                    row = conn.execute(
                        "SELECT pnl FROM trades WHERE side='SELL' AND symbol=? ORDER BY id DESC LIMIT 1",
                        (symbol,),
                    ).fetchone()
                    if row:
                        pnl = float(row["pnl"])
                if self.ledger.get_position(symbol) is None:
                    regime_now = detect_regime(self.provider)
                    self.paper_feedback.on_closed_trade(
                        symbol=symbol,
                        pnl=pnl,
                        entry_reason=str(meta.get("entry_reason") or d.explanation),
                        regime_at_entry=str(meta.get("regime") or "NEUTRAL"),
                        regime_at_exit=regime_now.value,
                        stop_distance_pct=float(meta.get("stop_distance_pct") or 0),
                        confidence=float(meta.get("confidence") or d.ai_confidence),
                        strategy=str(meta.get("strategy") or (d.alpha_summary or {}).get("label") or "ensemble"),
                    )
                    self._entry_meta.pop(symbol, None)
                    self._protect_state.pop(symbol, None)
            emit_order_lifecycle(
                self.alerts,
                symbol=symbol,
                side="SELL",
                result=result,
                strategy=d.decision.value,
                price=quote.price,
            )
            return {"ok": result.ok, "result": asdict(result), "alert_note": "ORDER event emitted (not SELL_SIGNAL)"}
        return {"ok": False, "message": f"no actionable signal ({d.decision.value})"}

    def monitor_exits(self) -> list[dict]:
        """Check stop/target vs marks; on hit execute paper sell then emit EXECUTION alerts.

        Also applies profit protection (breakeven / trail — never widen) and records
        post-trade lessons + calibration + strategy feedback (paper only).
        """
        out: list[dict] = []
        self.tick()
        regime_now = detect_regime(self.provider)
        for pos in list(self.ledger.positions()):
            quote = self.provider.get_quote(pos.symbol)
            self.ledger.mark_prices[pos.symbol] = quote.price
            bars = self.provider.get_bars(pos.symbol, 80)
            ind = compute_indicators(bars)
            meta = self._entry_meta.get(pos.symbol, {})
            entry = float(meta.get("entry") or pos.avg_cost)
            stop0 = float(meta.get("stop") or pos.stop_price or entry * 0.97)
            t1 = float(meta.get("target") or pos.target_price or entry * 1.03)
            # Synthetic T2/T3 for protection path when full plan not stored
            risk = max(entry - stop0, entry * 0.01)
            t2 = entry + risk * settings.preferred_risk_reward
            t3 = entry + risk * 3.0

            state = self._protect_state.get(pos.symbol)
            if state is None:
                state = initial_protect(entry, stop0)
                self._protect_state[pos.symbol] = state
            if ind is not None:
                momentum_ok = ind.ema9 >= ind.ema21
                state, exit_pct = update_profit_protection(
                    entry=entry,
                    price=quote.price,
                    stop=stop0,
                    ind=ind,
                    t1=t1,
                    t2=t2,
                    t3=t3,
                    state=state,
                    momentum_ok=momentum_ok,
                )
                self._protect_state[pos.symbol] = state
                if state.stop and (pos.stop_price is None or state.stop > float(pos.stop_price)):
                    self.ledger.update_stop(pos.symbol, state.stop)
                    pos = self.ledger.get_position(pos.symbol) or pos
            else:
                exit_pct = None

            kind = None
            tp_level = None
            qty = pos.quantity
            if pos.stop_price is not None and quote.price <= pos.stop_price:
                kind = "STOP_LOSS"
            elif exit_pct and exit_pct > 0 and quote.price >= t1:
                kind = "TAKE_PROFIT"
                tp_level = 1
                qty = max(1.0, round(pos.quantity * float(exit_pct), 4))
                if qty >= pos.quantity:
                    qty = pos.quantity
            elif pos.target_price is not None and quote.price >= pos.target_price:
                kind = "TAKE_PROFIT"
                tp_level = 1
            if not kind:
                continue
            order = OrderRequest(
                symbol=pos.symbol,
                side="SELL",
                quantity=qty,
                price=quote.price,
                reason=f"auto_exit:{kind}",
                client_order_id=f"EXIT:{kind}:{pos.symbol}:{quote.price}:{qty}",
            )
            result = self.broker.submit(order, pos.sector)
            emit_order_lifecycle(
                self.alerts, symbol=pos.symbol, side="SELL", result=result, price=quote.price, strategy=kind
            )
            if result.ok:
                emit_execution_exit(
                    self.alerts, symbol=pos.symbol, kind=kind, price=quote.price, tp_level=tp_level
                )
                # Paper feedback evaluation (CalibrationMonitor + lessons + strategy ranking)
                pnl = float(getattr(result, "pnl", 0) or 0)
                if pnl == 0:
                    # Broker may not echo pnl — approximate from ledger last sell
                    with self.ledger._connect() as conn:
                        row = conn.execute(
                            "SELECT pnl FROM trades WHERE side='SELL' AND symbol=? ORDER BY id DESC LIMIT 1",
                            (pos.symbol,),
                        ).fetchone()
                        if row:
                            pnl = float(row["pnl"])
                remaining = self.ledger.get_position(pos.symbol)
                if remaining is None:
                    review = self.paper_feedback.on_closed_trade(
                        symbol=pos.symbol,
                        pnl=pnl,
                        entry_reason=str(meta.get("entry_reason") or kind),
                        regime_at_entry=str(meta.get("regime") or "NEUTRAL"),
                        regime_at_exit=regime_now.value,
                        stop_distance_pct=float(meta.get("stop_distance_pct") or 0),
                        confidence=float(meta.get("confidence") or 50),
                        strategy=str(meta.get("strategy") or "ensemble"),
                    )
                    self._entry_meta.pop(pos.symbol, None)
                    self._protect_state.pop(pos.symbol, None)
                    out.append(
                        {
                            "symbol": pos.symbol,
                            "kind": kind,
                            "ok": result.ok,
                            "status": result.status,
                            "pnl": pnl,
                            "lessons": review.lessons,
                            "calibration_haircut": self.calibration.confidence_haircut,
                        }
                    )
                else:
                    out.append({"symbol": pos.symbol, "kind": kind, "ok": result.ok, "status": result.status, "partial": True})
            else:
                out.append({"symbol": pos.symbol, "kind": kind, "ok": result.ok, "status": result.status})
        return out

    def daily_summary_alert(self) -> dict:
        sells = []
        with self.ledger._connect() as conn:
            rows = conn.execute(
                "SELECT symbol, pnl FROM trades WHERE side='SELL' ORDER BY id DESC LIMIT 50"
            ).fetchall()
            sells = [(r["symbol"], float(r["pnl"])) for r in rows]
        winners = [p for _, p in sells if p > 0]
        losers = [p for _, p in sells if p <= 0]
        best = max(sells, key=lambda x: x[1]) if sells else ("—", 0)
        worst = min(sells, key=lambda x: x[1]) if sells else ("—", 0)
        total = len(sells)
        wr = (len(winners) / total * 100) if total else 0.0
        unrealized = self.ledger.holdings_value() - sum(
            p.quantity * p.avg_cost for p in self.ledger.positions()
        )
        payload = {
            "date": date.today().isoformat(),
            "total_trades": total,
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": f"%{wr:.1f}",
            "realized_pnl": round(sum(p for _, p in sells), 2),
            "unrealized_pnl": round(unrealized, 2),
            "drawdown_pct": round(self.ledger.drawdown_pct(), 2),
            "best_trade": f"{best[0]} ({best[1]:.2f})",
            "worst_trade": f"{worst[0]} ({worst[1]:.2f})",
            "open_positions": self.ledger.open_position_count(),
            "risk_level": self.capital_mode.value,
        }
        emit_daily_summary(self.alerts, payload)
        return payload
