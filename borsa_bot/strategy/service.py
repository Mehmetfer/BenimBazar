from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from ai.quality import assess_signal_quality, classify_volatility_regime
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
from data.integrity import FreshnessStatus, format_age_tr
from data.provenance import (
    MixedProvenanceError,
    assert_homogeneous_provenance,
    is_live_provider_configured,
    kind_of,
    live_provider_status,
    provenance_payload,
    tradeable_flag,
)
from data.validation import gate_market_data_for_scan, normalize_app_env, validate_quote_bars_homogeneous
from execution.paper import PaperBroker
from execution.safety import SafetyGate
from factors.engine import compute_factors
from fundamental.provider import get_fundamentals, score_fundamentals
from indicators.engine import compute_indicators
from market_regime.engine import detect_regime, trend_label
from news.analyzer import classify_headline, latest_stub_headline, score_news
from portfolio.construction import build_correlation_matrix, size_position
from portfolio.ledger import PortfolioLedger
from portfolio.wallet_view import paper_wallet_snapshot
from profit.ev import compute_opportunity, decide_matrix, dynamic_size_multiplier
from profit.modes import select_capital_mode
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
        self.multi = MultiHorizonOrchestrator(self.provider, equity=settings.starting_cash)
        self._last_risk_alert_reason = ""
        self._kill_switch_alerted = False
        self._emit_signal_alerts = True  # dashboard/scan may publish SIGNAL alerts (not fills)
        self._last_favorite_scan_ts = 0.0
        self._favorite_deeper_cache: dict[str, dict] = {}
        self._prediction_cards: dict[str, dict] = {}
        self._market_gate = None
        self._scan_cache: list[SymbolDecision] | None = None
        self._scan_cache_ts: float = 0.0

    def _invalidate_scan_cache(self) -> None:
        self._scan_cache = None
        self._scan_cache_ts = 0.0

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
            "app_env": settings.normalized_app_env,
            "capital_mode": self.capital_mode.value,
            "data_fresh": data_fresh_for_safety,
            "kill_switch": settings.kill_switch,
            "paused": self.risk.paused,
            "safety_ok": ok,
            "live_preflight_ok": live_ok,
            "live_preflight_failed": live_failed,
            "live_ready": live_ready,
            "live_trading": False,
            "manual_approval": settings.require_manual_approval,
            "error": self.last_error,
            "market_data_gate": (self._market_gate.to_dict() if self._market_gate else None),
            "objectives": SYSTEM_OBJECTIVES,
            "philosophy": (
                "LESS DATA, MORE DECISION. "
                "Sermaye koruma → risk kontrolü → yüksek olasılıklı fırsat. "
                "NO_TRADE birinci sınıf. Uydurma veri yasak. "
                "SİMÜLE ≠ CANLI. TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK. "
                "LIVE READY yalnızca doğrulanmış piyasa + broker ile."
            ),
            "strategy_ranking_example": example_ranking_report(),
            "data_source": meta.to_dict(),
            "live_data_provider": live_provider_status(
                configured=is_live_provider_configured(),
                connected=bool(meta.is_live_market and meta.connected),
            ),
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

    def tick(self) -> None:
        self.provider.tick()
        self._invalidate_scan_cache()

    def scan(self, symbols: list[str] | None = None) -> list[SymbolDecision]:
        import time

        cache_ttl = max(30.0, float(settings.data_freshness_sec) * 2)
        now = time.time()
        if (
            symbols is None
            and self._scan_cache is not None
            and (now - self._scan_cache_ts) < cache_ttl
        ):
            return list(self._scan_cache)
        if symbols is not None and self._scan_cache is not None and (now - self._scan_cache_ts) < cache_ttl:
            want = {s.upper() for s in symbols}
            filtered = [d for d in self._scan_cache if d.symbol in want]
            if filtered:
                return filtered
        # DATA NOT VERIFIED → NO SIGNAL (does not change decide_matrix math)
        gate = gate_market_data_for_scan(
            self.provider,
            app_env=settings.app_env,
            max_age_sec=settings.data_freshness_sec,
        )
        self._market_gate = gate
        if not gate.signals_allowed:
            self.last_error = f"{gate.code.value}: {gate.note}"
            return []

        self.tick()
        # No fabricated scan when live source required / unavailable
        if not self.provider.has_market_data():
            self.last_error = "NO_MARKET_DATA"
            return []
        # Evaluate matured forecasts against current marks (measurement only)
        try:
            def _px(sym: str) -> float | None:
                try:
                    return float(self.provider.get_quote(sym).price)
                except Exception:  # noqa: BLE001
                    return None

            meta_kind = kind_of(self.provider.source_meta(settings.data_freshness_sec))
            self.predictions.evaluate_due(_px, actual_result_source=meta_kind.value)
        except Exception:  # noqa: BLE001
            pass
        try:
            regime = detect_regime(self.provider)
        except Exception:  # noqa: BLE001
            from config.models import MarketRegime as _MR

            regime = _MR.NEUTRAL
        try:
            index_bars = self.provider.get_bars("XU100", 220)
            index_ind = compute_indicators(index_bars)
        except Exception:  # noqa: BLE001
            index_bars, index_ind = [], None
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
        )
        self.risk.capital_mode = self.capital_mode
        meta_kind = str(
            getattr(getattr(self.provider.source_meta(settings.data_freshness_sec), "kind", None), "value", "")
            or ""
        ).upper()
        provider_id = str(getattr(self.provider, "provider_id", "") or "").lower()
        delayed_feed = meta_kind in {"DELAYED", "REQUIRED"} or "yahoo" in provider_id or provider_id == "session_auto"
        # Full-universe bar evaluation is unsafe on Yahoo DELAYED (100 chart pulls → 429).
        if delayed_feed:
            universe_map = {}
        else:
            universe_map = {m.symbol: m for m in select_universe(self.provider)}
        # Correlation series for book awareness — NEVER fetch bars for full universe on
        # Yahoo/DELAYED (100 chart calls → 429 / page hang). Positions + favorites only.
        ret_series: dict[str, list[float]] = {}
        corr_syms = {p.symbol for p in self.ledger.positions()} | set(self.favorites.symbols())
        if not delayed_feed:
            corr_syms |= set(self.provider.list_symbols())
        for symbol in corr_syms:
            try:
                bars_c = self.provider.get_bars(symbol, 40)
            except Exception:  # noqa: BLE001
                continue
            closes = [b.close for b in bars_c]
            ret_series[symbol] = [
                closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]
            ]
        corr_matrix = build_correlation_matrix(ret_series) if ret_series else {}

        # Priority queue: FAVORITES → rest of market (does not skip non-favorites)
        fav_set = self.favorites.symbols()
        all_syms = [s for s in self.provider.list_symbols() if s != "XU100"]
        if symbols:
            want = {s.upper() for s in symbols}
            all_syms = [s for s in all_syms if s in want]
        ordered = [s for s in all_syms if s in fav_set] + [s for s in all_syms if s not in fav_set]
        # Cap deep Yahoo analysis so /api/daily cannot hang on 100 sequential chart pulls
        if delayed_feed and symbols is None:
            deep_cap = max(5, min(8, int(getattr(settings, "autonomy_deep_max", 8))))
            owned = {p.symbol for p in self.ledger.positions()}
            priority = [s for s in ordered if s in fav_set or s in owned]
            rest = [s for s in ordered if s not in fav_set and s not in owned]
            ordered = (priority + rest)[:deep_cap]
            # Prefetch bars in small parallel batches (Yahoo chart is the bottleneck)
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _prefetch(sym: str) -> None:
                try:
                    self.provider.get_bars(sym, 240)
                except Exception:  # noqa: BLE001
                    return

            try:
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futs = [pool.submit(_prefetch, s) for s in ordered[:deep_cap]]
                    futs.append(pool.submit(_prefetch, "XU100"))
                    for fut in as_completed(futs, timeout=40):
                        try:
                            fut.result()
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001
                pass

        for symbol in ordered:
            try:
                quote = self.provider.get_quote(symbol)
            except Exception:  # noqa: BLE001
                continue
            marks[symbol] = quote.price
            uni = universe_map.get(symbol)
            try:
                bars = self.provider.get_bars(symbol, 240)
            except Exception:  # noqa: BLE001
                continue
            if not bars:
                continue
            # Mixed LIVE + SIMULATED (etc.) must not enter one calculation
            env = normalize_app_env(settings.app_env)
            try:
                assert_homogeneous_provenance(
                    [kind_of(quote), *[kind_of(b) for b in bars]],
                    context=f"scan/{symbol}",
                )
            except MixedProvenanceError:
                continue
            hom = validate_quote_bars_homogeneous(quote, bars, env=env)
            if not hom.ok:
                continue
            ind = compute_indicators(bars)
            if ind is None:
                continue
            try:
                src_kind = assert_homogeneous_provenance(
                    [kind_of(quote), kind_of(ind)],
                    context=f"scan/{symbol}/indicator",
                )
            except MixedProvenanceError:
                continue
            # UNKNOWN / non-live never tradeable for live signals; paper may still record SIMULATED
            src_tradeable = tradeable_flag(src_kind, verified=False)
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
            size_mult = 0.0
            if opp:
                size_mult = dynamic_size_multiplier(opp, capital_mode=self.capital_mode, regime=regime)
                opp.position_size_mult = size_mult

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
            bundle.ai_confidence = ai_conf

            reasons = tech_reasons + vol_notes + fund_notes + sector_notes + news_notes + liq_notes
            reasons.append(f"ensemble_bias={bias}")
            reasons.append(f"alpha_bias={alpha_bias}/{alpha_label}")
            reasons.append(f"capital_mode={self.capital_mode.value}")
            reasons.append(f"price_action={pa.pattern}")
            reasons.extend(alpha_notes[:2])
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
                data_source_kind=src_kind.value,
                tradeable=src_tradeable,
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
                    market_data_source=src_kind.value,
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
                        "data_source_kind": src_kind.value,
                        "tradeable": src_tradeable,
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
                    "data_source_kind": d.data_source_kind,
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
        if symbols is None:
            self._scan_cache = list(decisions)
            self._scan_cache_ts = time.time()
        return decisions

    def bist100_quotes(self) -> dict:
        """Fast BIST100 quote board — Son/Alış/Satış/%G (no deep scan)."""
        from universe.bist100 import list_companies

        try:
            self.tick()
        except Exception:  # noqa: BLE001
            pass
        source = self.provider.source_meta(settings.data_freshness_sec)

        def _row(sym: str, name: str, sector: str = "", tv: str = "") -> dict:
            try:
                q = self.provider.get_quote(sym)
                chg = float(getattr(q, "change_pct", 0) or 0)
                ts = q.ts.isoformat() if hasattr(q.ts, "isoformat") else None
                return {
                    "symbol": sym,
                    "ticker": sym,
                    "name": name,
                    "sector": sector,
                    "price": round(float(q.price), 4),
                    "bid": round(float(q.bid), 4) if q.bid else None,
                    "ask": round(float(q.ask), 4) if q.ask else None,
                    "change_pct": round(chg, 2),
                    "quote_ts": ts,
                    "tradingview_symbol": tv or f"BIST:{sym}",
                    "decision": None,
                    "decision_label": None,
                }
            except Exception:  # noqa: BLE001
                return {
                    "symbol": sym,
                    "ticker": sym,
                    "name": name,
                    "sector": sector,
                    "price": None,
                    "bid": None,
                    "ask": None,
                    "change_pct": None,
                    "tradingview_symbol": tv or f"BIST:{sym}",
                    "decision": "NO_DATA",
                    "decision_label": "VERİ YOK",
                }

        index = _row("XU100", "BIST 100", "Endeks", "BIST:XU100")
        quotes = [_row(c.ticker, c.name, c.sector, c.tradingview_symbol) for c in list_companies()]
        session = getattr(source, "market_session", None)
        session_val = session.value if hasattr(session, "value") else str(session or "")
        return {
            "ok": True,
            "index": index,
            "quotes": quotes,
            "count": len(quotes),
            "with_price": sum(1 for q in quotes if q.get("price") is not None),
            "data_source": source.to_dict(),
            "market_session": session_val,
            "price_label": getattr(source, "price_label", None),
            "note": (
                "Piyasa kapalı · gösterilenler son kapanış / gecikmeli fiyat"
                if session_val == "CLOSED"
                else "Hızlı kotasyon — sinyal analizi ayrı yüklenir"
            ),
        }

    def watchlist_quotes(self) -> dict:
        """Fast Takip Listem board — XU100 + favorites, Son/Alış/Satış/%G."""
        from universe.bist100 import get_company

        self.favorites.ensure_default_watchlist(market_type="BIST")
        try:
            self.tick()
        except Exception:  # noqa: BLE001
            pass
        source = self.provider.source_meta(settings.data_freshness_sec)

        def _name_for(sym: str) -> tuple[str, str]:
            c = get_company(sym)
            if c:
                return c.name, c.sector
            if sym == "XU100":
                return "BIST 100", "Endeks"
            return sym, ""

        def _row(sym: str, *, is_favorite: bool = False) -> dict:
            name, sector = _name_for(sym)
            try:
                q = self.provider.get_quote(sym)
                chg = float(getattr(q, "change_pct", 0) or 0)
                ts = q.ts.isoformat() if hasattr(q.ts, "isoformat") else None
                return {
                    "symbol": sym,
                    "ticker": sym,
                    "name": name,
                    "sector": sector,
                    "price": round(float(q.price), 4),
                    "bid": round(float(q.bid), 4) if q.bid else None,
                    "ask": round(float(q.ask), 4) if q.ask else None,
                    "change_pct": round(chg, 2),
                    "quote_ts": ts,
                    "is_favorite": is_favorite,
                    "decision": None,
                    "decision_label": None,
                }
            except Exception:  # noqa: BLE001
                return {
                    "symbol": sym,
                    "ticker": sym,
                    "name": name,
                    "sector": sector,
                    "price": None,
                    "bid": None,
                    "ask": None,
                    "change_pct": None,
                    "is_favorite": is_favorite,
                    "decision": "NO_DATA",
                    "decision_label": "VERİ YOK",
                }

        index = _row("XU100")
        quotes = []
        for fav in self.favorites.list_favorites(market_type="BIST"):
            sym = fav.symbol.upper()
            if sym == "XU100":
                continue
            quotes.append(_row(sym, is_favorite=True))
        return {
            "ok": True,
            "index": index,
            "quotes": quotes,
            "count": len(quotes),
            "data_source": source.to_dict(),
            "note": "Takip listesi — hızlı kotasyon",
        }

    def bist100_analysis(
        self,
        *,
        q: str | None = None,
        sector: str | None = None,
        sort: str = "decision",
    ) -> dict:
        """Full BIST 100 scan merged with catalog metadata — one row per company."""
        from dashboard.daily import _label_tr
        from universe.bist100 import catalog_payload, filter_companies

        meta = catalog_payload(q=q, sector=sector)
        companies = filter_companies(q=q, sector=sector)
        tickers = {c.ticker for c in companies}
        decisions = {d.symbol: d for d in self.scan()}
        gate = self._market_gate
        source = self.provider.source_meta(settings.data_freshness_sec)

        rows: list[dict] = []
        for c in companies:
            d = decisions.get(c.ticker)
            if d is not None:
                row = self._serialize(d)
                row["tradingview_symbol"] = c.tradingview_symbol
                row["decision_label"] = _label_tr(
                    str(row.get("final_decision") or row.get("decision") or "")
                )
                row["final_score"] = float((row.get("scores") or {}).get("final") or row.get("buy_score") or 0)
                pos = self.ledger.get_position(c.ticker)
                row["position_qty"] = float(pos.quantity) if pos else 0
            else:
                in_port = self.ledger.get_position(c.ticker)
                row = {
                    "symbol": c.ticker,
                    "ticker": c.ticker,
                    "name": c.name,
                    "sector": c.sector,
                    "tradingview_symbol": c.tradingview_symbol,
                    "price": None,
                    "change_pct": None,
                    "decision": "NO_DATA",
                    "decision_label": "VERİ YOK",
                    "final_score": 0.0,
                    "ai_confidence": None,
                    "scanner_class": "NO_TRADE",
                    "note": "Tarama kapsamı dışında veya veri yok",
                    "in_portfolio": in_port is not None,
                    "position_qty": float(in_port.quantity) if in_port else 0,
                }
            rows.append(row)

        sort_key = (sort or "decision").lower()
        if sort_key == "alpha":
            rows.sort(key=lambda r: str(r.get("symbol") or ""))
        elif sort_key == "score":
            rows.sort(key=lambda r: -float(r.get("final_score") or 0))
        else:
            # default: Güçlü AL → AL → … then skor (yüksek üstte)
            from dashboard.daily import SIGNAL_RANK

            def _decision_rank(row: dict) -> int:
                dec = str(row.get("final_decision") or row.get("decision") or "").upper()
                return SIGNAL_RANK.get(dec, 50)

            rows.sort(
                key=lambda r: (
                    _decision_rank(r),
                    -float(r.get("final_score") or 0),
                    str(r.get("symbol") or ""),
                )
            )

        summary: dict[str, int] = {
            "STRONG_BUY": 0,
            "BUY": 0,
            "WATCH": 0,
            "WAIT": 0,
            "SELL": 0,
            "NO_TRADE": 0,
            "NO_DATA": 0,
        }
        for r in rows:
            dec = str(r.get("decision") or "NO_DATA").upper()
            if dec in {"AL"}:
                summary["BUY"] += 1
            elif dec in summary:
                summary[dec] += 1
            elif dec in {"BEKLE", "HOLD"}:
                summary["WAIT"] += 1
            else:
                summary["NO_TRADE"] += 1

        return {
            **meta,
            "companies": rows,
            "count": len(rows),
            "analyzed": sum(1 for r in rows if r.get("price") is not None),
            "summary": summary,
            "sort": sort_key if sort_key != "decision" else "decision_score",
            "sort_label": "Güçlü AL → AL → skor",
            "data_source": source.to_dict(),
            "market_data_gate": gate.to_dict() if gate else {},
            "principle": "BIST 100 tam tarama · SIGNAL ≠ EMİR · PAPER ONLY",
            "note": (
                f"{summary['STRONG_BUY']} Güçlü AL · {summary['BUY']} AL · "
                f"{summary['WATCH']} İzle · {summary['WAIT']} Bekle · "
                f"kaynak: {source.display_name}"
            ),
        }

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
        gate = self._market_gate or gate_market_data_for_scan(
            self.provider,
            app_env=settings.app_env,
            max_age_sec=settings.data_freshness_sec,
        )
        self._market_gate = gate
        signals_paused = (
            (not gate.signals_allowed)
            or meta.freshness
            in {
                FreshnessStatus.STALE,
                FreshnessStatus.DISCONNECTED,
                FreshnessStatus.NO_DATA,
            }
            or not self.provider.has_market_data()
        )
        daily = build_daily_home(
            universe,
            meta,
            signal_ttl_sec=settings.signal_ttl_sec,
            top_n=settings.daily_top_n,
            signals_paused=signals_paused,
        )
        if not gate.signals_allowed:
            daily["no_opportunity"] = True
            daily["no_opportunity_message"] = (
                "MARKET DATA UNAVAILABLE — "
                f"{gate.code.value}: {gate.note}"
            )
            daily["market_data_gate"] = gate.to_dict()
        else:
            daily["market_data_gate"] = gate.to_dict()

        return {
            "health": health,
            "principle": "LESS DATA, MORE DECISION · FAVORITE ≠ BUY · SİMÜLE ≠ CANLI · PROD MOCK HARD BLOCK",
            "daily": daily,
            "app_env": settings.normalized_app_env,
            "market_data_gate": gate.to_dict(),
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
            "live_trading": False,
        }

    def _serialize(self, d: SymbolDecision) -> dict:
        fav = bool(getattr(d, "_is_favorite", self.favorites.is_favorite(d.symbol)))
        fav_rec = self.favorites.get(d.symbol) if fav else None
        in_portfolio = self.ledger.get_position(d.symbol) is not None
        pos = self.ledger.get_position(d.symbol)
        change_pct = 0.0
        prev_close = None
        quote_ts = None
        bid = ask = None
        try:
            quote = self.provider.get_quote(d.symbol)
            bid = round(float(quote.bid), 4) if quote.bid else None
            ask = round(float(quote.ask), 4) if quote.ask else None
            if getattr(quote, "change_pct", None) is not None:
                change_pct = float(quote.change_pct)
            if hasattr(quote, "ts") and quote.ts:
                quote_ts = quote.ts.isoformat() if hasattr(quote.ts, "isoformat") else str(quote.ts)
            bars = self.provider.get_bars(d.symbol, 3)
            if bars and not quote_ts:
                quote_ts = bars[-1].ts.isoformat() if hasattr(bars[-1].ts, "isoformat") else str(bars[-1].ts)
            if len(bars) >= 2 and bars[-2].close and change_pct == 0.0:
                prev_close = round(bars[-2].close, 2)
                change_pct = (bars[-1].close / bars[-2].close - 1) * 100
        except Exception:  # noqa: BLE001
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
            "bid": bid,
            "ask": ask,
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
            "data_source_kind": getattr(d, "data_source_kind", None) or "UNKNOWN",
            "tradeable": bool(getattr(d, "tradeable", False)),
            **provenance_payload(getattr(d, "data_source_kind", None) or "UNKNOWN", verified=False),
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
            return {"ok": False, "message": "LIVE mode blocked — paper trading zorunlu", "live_trading": False}
        gate = gate_market_data_for_scan(
            self.provider,
            app_env=settings.app_env,
            max_age_sec=settings.data_freshness_sec,
        )
        self._market_gate = gate
        if not gate.signals_allowed:
            return {
                "ok": False,
                "message": f"{gate.code.value} — trading blocked",
                "auto_trading": False,
                "live_trading": False,
                "market_data_gate": gate.to_dict(),
            }
        if not self.provider.has_market_data():
            return {
                "ok": False,
                "message": "DATA SOURCE REQUIRED — canlı/paper veri yok, emir yok",
                "auto_trading": False,
                "live_trading": False,
            }
        meta = self.provider.source_meta(settings.data_freshness_sec)
        if meta.freshness.value in {"STALE", "DISCONNECTED", "NO_DATA"}:
            return {
                "ok": False,
                "message": "STALE/DISCONNECTED data — auto trading disabled",
                "auto_trading": False,
                "live_trading": False,
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
                client_order_id=f"MANUAL-BUY:{symbol}:{utc_now().strftime('%Y%m%d%H%M')}",
            )
            result = self.broker.submit(order, quote.sector)
            self.pending_approvals.pop(symbol, None)
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
                client_order_id=f"MANUAL-SELL:{symbol}:{utc_now().strftime('%Y%m%d%H%M')}",
            )
            result = self.broker.submit(order, quote.sector)
            self.pending_approvals.pop(symbol, None)
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

    def execute_manual_paper(
        self,
        symbol: str,
        side: str,
        *,
        quantity: float | None = None,
        price: float | None = None,
    ) -> dict:
        """Manual BIST paper BUY/SELL — signal-independent; optional qty/price."""
        symbol = symbol.upper()
        side_u = side.upper()
        if side_u not in {"BUY", "SELL"}:
            return {"ok": False, "message": "side BUY veya SELL olmalı"}

        if settings.is_live:
            return {"ok": False, "message": "LIVE mode blocked — paper trading zorunlu", "live_trading": False}

        gate = gate_market_data_for_scan(
            self.provider,
            app_env=settings.app_env,
            max_age_sec=settings.data_freshness_sec,
        )
        self._market_gate = gate
        if not gate.signals_allowed:
            return {"ok": False, "message": f"{gate.code.value} — trading blocked", "market_data_gate": gate.to_dict()}
        if not self.provider.has_market_data():
            return {"ok": False, "message": "DATA SOURCE REQUIRED — veri yok, emir yok"}

        meta = self.provider.source_meta(settings.data_freshness_sec)
        if meta.freshness.value in {"STALE", "DISCONNECTED", "NO_DATA"}:
            return {"ok": False, "message": "STALE/DISCONNECTED data — emir engellendi"}

        try:
            quote = self.provider.get_quote(symbol)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"quote unavailable: {exc}"}

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

        if price is not None and float(price) > 0:
            fill_price = float(price)
        elif side_u == "SELL":
            fill_price = float(quote.bid) if float(getattr(quote, "bid", 0) or 0) > 0 else float(quote.price)
        else:
            fill_price = float(quote.ask) if float(getattr(quote, "ask", 0) or 0) > 0 else float(quote.price)

        if side_u == "SELL":
            pos = self.ledger.get_position(symbol)
            if not pos:
                return {"ok": False, "message": "Portföyde pozisyon yok"}
            sell_qty = int(quantity) if quantity is not None else int(pos.quantity)
            if sell_qty <= 0:
                return {"ok": False, "message": "Adet 0'dan büyük olmalı"}
            if sell_qty > int(pos.quantity):
                return {"ok": False, "message": f"En fazla {int(pos.quantity)} lot satılabilir"}
            rd = self.risk.evaluate_exit(symbol, SignalAction.SELL)
            if not rd.allowed:
                return {"ok": False, "message": rd.reason}
            order = OrderRequest(
                symbol=symbol,
                side="SELL",
                quantity=float(sell_qty),
                price=fill_price,
                reason="manual_ui_sell",
                client_order_id=f"MANUAL-UI-SELL:{symbol}:{utc_now().strftime('%Y%m%d%H%M%S')}",
            )
            result = self.broker.submit(order, quote.sector)
            emit_order_lifecycle(
                self.alerts,
                symbol=symbol,
                side="SELL",
                result=result,
                strategy="MANUAL_UI",
                price=fill_price,
            )
            return {
                "ok": result.ok,
                "side": "SELL",
                "symbol": symbol,
                "quantity": sell_qty,
                "price": fill_price,
                "result": asdict(result),
                "wallet": self.paper_wallet(),
            }

        d = None
        if quantity is None:
            decisions = {x.symbol: x for x in self.scan()}
            d = decisions.get(symbol)

        if side_u == "BUY":
            custom_qty = int(quantity) if quantity is not None else None
            if custom_qty is not None and custom_qty <= 0:
                return {"ok": False, "message": "Adet 0'dan büyük olmalı"}
            existing = self.ledger.get_position(symbol)
            if existing is None and self.ledger.open_position_count() >= int(settings.max_open_positions):
                return {"ok": False, "message": "max_open_positions"}
            bars = self.provider.get_bars(symbol, 220)
            ind = compute_indicators(bars)
            plan = d.trade_plan if d else None
            stop_price = None
            target_price = None
            qty = custom_qty
            if qty is None:
                size_mult = float(d.opportunity.position_size_mult) if d and d.opportunity else 0.75
                rd = self.risk.evaluate_entry(
                    symbol=symbol,
                    sector=quote.sector,
                    price=fill_price,
                    ind=ind,
                    action=SignalAction.BUY,
                    plan=plan,
                    spread_pct=quote.spread_pct,
                    correlated_sector_risk=self.ledger.sector_risk_pct(quote.sector),
                    opportunity=None,
                    capital_mode=self.capital_mode,
                    size_mult=size_mult,
                )
                if not rd.allowed:
                    return {"ok": False, "message": rd.reason, "risk": rd.risk.value}
                qty = int(rd.quantity)
                stop_price = rd.stop_price
                target_price = rd.target_price
            else:
                cost = qty * fill_price
                if cost > self.ledger.cash + 1e-6:
                    return {"ok": False, "message": f"Yetersiz bakiye — gerekli {cost:,.2f} TL"}
                stop = fill_price - ind.atr14 * settings.atr_stop_mult
                risk_ps = fill_price - stop
                if risk_ps <= 0:
                    return {"ok": False, "message": "stop_undefined"}
                stop_price = round(stop, 2)
                target_price = round(fill_price + risk_ps * settings.min_risk_reward, 2)
            order = OrderRequest(
                symbol=symbol,
                side="BUY",
                quantity=float(qty),
                price=fill_price,
                reason="manual_ui_buy",
                stop_price=stop_price,
                target_price=target_price,
                client_order_id=f"MANUAL-UI-BUY:{symbol}:{utc_now().strftime('%Y%m%d%H%M%S')}",
            )
            result = self.broker.submit(order, quote.sector)
            emit_order_lifecycle(
                self.alerts,
                symbol=symbol,
                side="BUY",
                result=result,
                strategy="MANUAL_UI",
                price=fill_price,
            )
            return {
                "ok": result.ok,
                "side": "BUY",
                "symbol": symbol,
                "quantity": qty,
                "price": fill_price,
                "result": asdict(result),
                "wallet": self.paper_wallet(),
            }

        return {"ok": False, "message": "side BUY veya SELL olmalı"}

    def monitor_exits(self) -> list[dict]:
        """Trailing stops, partial TPs, then stop/target exits."""
        from autonomous.monitor import monitor_and_exit

        return monitor_and_exit(self, execution_mode="PAPER")

    def _monitor_exits_core(self) -> list[dict]:
        """Check stop/target vs marks; on hit execute paper sell then emit EXECUTION alerts."""
        out: list[dict] = []
        self.tick()
        for pos in list(self.ledger.positions()):
            quote = self.provider.get_quote(pos.symbol)
            self.ledger.mark_prices[pos.symbol] = quote.price
            kind = None
            tp_level = None
            if pos.stop_price is not None and quote.price <= pos.stop_price:
                kind = "STOP_LOSS"
            elif pos.target_price is not None and quote.price >= pos.target_price:
                kind = "TAKE_PROFIT"
                tp_level = 1
            if not kind:
                continue
            order = OrderRequest(
                symbol=pos.symbol,
                side="SELL",
                quantity=pos.quantity,
                price=quote.price,
                reason=f"auto_exit:{kind}",
                client_order_id=f"EXIT:{kind}:{pos.symbol}:{quote.price}",
            )
            result = self.broker.submit(order, pos.sector)
            emit_order_lifecycle(
                self.alerts, symbol=pos.symbol, side="SELL", result=result, price=quote.price, strategy=kind
            )
            if result.ok:
                emit_execution_exit(
                    self.alerts, symbol=pos.symbol, kind=kind, price=quote.price, tp_level=tp_level
                )
            out.append({"symbol": pos.symbol, "kind": kind, "ok": result.ok, "status": result.status})
        return out

    def paper_wallet(self) -> dict:
        """BIST paper wallet snapshot — simulation only."""
        self.tick()
        marks: dict[str, float] = {}
        for p in self.ledger.positions():
            try:
                marks[p.symbol] = float(self.provider.get_quote(p.symbol).price)
            except Exception:  # noqa: BLE001
                marks[p.symbol] = p.avg_cost
        self.ledger.set_marks(marks)
        snap = paper_wallet_snapshot(self.ledger)
        snap["auto_follow"] = bool(getattr(settings, "bist_paper_auto_follow", False))
        snap["max_open_positions"] = int(settings.max_open_positions)
        return snap

    def follow_recommendations(self, *, max_buys: int = 2) -> dict:
        """Paper-buy BIST STRONG_BUY/BUY recommendations; auto-exit on SAT/stop/target."""
        from dashboard.daily import SIGNAL_RANK
        from profit.costs import edge_below_cost_reason

        if not bool(getattr(settings, "bist_paper_auto_follow", False)):
            return {"ok": False, "skipped": "BIST_PAPER_AUTO_FOLLOW=false"}

        # Simulated / stub books are for plumbing tests — not an edge source.
        meta = self.provider.source_meta(settings.data_freshness_sec)
        kind = str(getattr(getattr(meta, "kind", None), "value", "") or "").upper()
        provider_id = str(getattr(self.provider, "provider_id", "") or "").lower()
        simulated = (
            kind in {"SIMULATED", "TEST", "BACKTEST", "MOCK"}
            or "simulated" in provider_id
            or str(getattr(settings, "data_provider", "")).lower() in {"simulated", "sim", "mock"}
        )
        if simulated:
            exits = self.monitor_exits()
            return {
                "ok": False,
                "skipped": "SIMULATED_DATA_NO_AUTO_TRADE",
                "exits": exits,
                "note": "Auto-follow blocked on simulated/mock data — prevents noise stop-outs claiming edge",
                "wallet": self.paper_wallet(),
            }

        exits = self.monitor_exits()
        decisions = self.scan()
        if not decisions:
            return {"ok": True, "buys": [], "sells": [], "exits": exits, "note": "no scan data"}

        buy_candidates: list[Any] = []
        sell_candidates: list[Any] = []
        for d in decisions:
            dec = str(d.final_decision or d.decision.value).upper()
            if dec in {"STRONG_BUY", "BUY", "AL"}:
                buy_candidates.append(d)
            elif dec in {"SELL", "SAT", "STRONG_SELL"} and self.ledger.get_position(d.symbol):
                sell_candidates.append(d)

        def _rank(d: Any) -> tuple:
            dec = str(d.final_decision or d.decision.value).upper()
            return (SIGNAL_RANK.get(dec, 50), -float(d.buy_score or 0), d.symbol)

        buy_candidates.sort(key=_rank)

        results: dict[str, Any] = {"buys": [], "sells": [], "exits": exits, "skipped_buys": []}
        for d in sell_candidates:
            r = self.execute_signal(d.symbol, approved=True)
            results["sells"].append(
                {"symbol": d.symbol, "decision": d.decision.value, "ok": r.get("ok"), "message": r.get("message")}
            )

        bought = 0
        cap = max(1, min(5, int(max_buys)))
        for d in buy_candidates:
            if bought >= cap:
                break
            if self.ledger.get_position(d.symbol) is not None:
                continue
            if self.ledger.open_position_count() >= int(settings.max_open_positions):
                break
            opp = getattr(d, "opportunity", None)
            net_ev = float(getattr(opp, "expected_value", 0) or 0) if opp else 0.0
            # expected_value is already NET of round-trip costs
            if opp is None or net_ev <= float(settings.min_expected_value) or net_ev <= 0:
                results["skipped_buys"].append(
                    {
                        "symbol": d.symbol,
                        "reason": edge_below_cost_reason(net_ev) if opp else "no_opportunity",
                        "net_ev": net_ev,
                    }
                )
                continue
            r = self.execute_signal(d.symbol, approved=True)
            row = {
                "symbol": d.symbol,
                "decision": d.decision.value,
                "score": round(float(d.buy_score or 0), 1),
                "ok": bool(r.get("ok")),
                "message": r.get("message"),
            }
            results["buys"].append(row)
            if r.get("ok"):
                bought += 1

        results["ok"] = True
        results["bought"] = bought
        results["wallet"] = self.paper_wallet()
        return results

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

    def _overlay_signal_lite(self, symbol: str, quote) -> dict | None:
        """Fast display-only AL/SAT/Bekle scores for stock overlay (not an order)."""
        from indicators.engine import compute_indicators
        from signals.engine import score_sell, technical_score

        try:
            bars = self.provider.get_bars(symbol, 240)
        except Exception:  # noqa: BLE001
            return None
        if not bars or len(bars) < 210 or quote is None:
            return None
        ind = compute_indicators(bars)
        if ind is None:
            return None
        buy, _reasons = technical_score(ind, float(quote.price))
        owned = self.ledger.get_position(symbol) is not None
        sell = score_sell(ind, float(quote.price), float(getattr(quote, "volume", 0) or 0), owned)
        strong_th = float(getattr(settings, "strong_buy_threshold", 75))
        buy_th = float(getattr(settings, "buy_score_threshold", 60))
        sell_th = float(getattr(settings, "sell_score_threshold", 60))
        if owned and sell >= sell_th + 10:
            dec, label = "STRONG_SELL", "Güçlü SAT"
        elif owned and sell >= sell_th:
            dec, label = "SELL", "SAT"
        elif buy >= strong_th:
            dec, label = "STRONG_BUY", "Güçlü AL"
        elif buy >= buy_th:
            dec, label = "BUY", "AL"
        elif sell >= sell_th and buy < 45:
            dec, label = "SELL", "SAT"
        elif buy >= 45:
            dec, label = "WAIT", "Bekle"
        else:
            dec, label = "WAIT", "Bekle"
        return {
            "decision": dec,
            "final_decision": dec,
            "decision_label": label,
            "buy_score": round(float(buy), 1),
            "sell_score": round(float(sell), 1),
            "priority_score": round(float(buy), 1),
            "signal_source": "overlay_lite",
        }

    def symbol_board(self, symbol: str) -> dict:
        """Rich stock detail payload for overlay — quote, signal, scores, returns, KAP link."""
        from universe.bist100 import get_company

        sym = str(symbol or "").upper().strip()
        company = get_company(sym)
        meta = self.provider.source_meta(settings.data_freshness_sec)
        session = getattr(meta, "market_session", None)
        session_val = session.value if hasattr(session, "value") else str(session or "UNKNOWN")

        quote = None
        try:
            self.tick()
            quote = self.provider.get_quote(sym)
        except Exception:  # noqa: BLE001
            quote = None

        fav_rec = self.favorites.get(sym, market_type="BIST")
        is_fav = bool(fav_rec and fav_rec.active)
        pos = self.ledger.get_position(sym)

        pack: dict = {}
        try:
            fn = getattr(self.provider, "board_market_pack", None) or getattr(self.provider, "period_returns", None)
            if callable(fn):
                pack = fn(sym) or {}
        except Exception:  # noqa: BLE001
            pack = {}
        returns = {
            "daily_pct": pack.get("daily_pct"),
            "weekly_pct": pack.get("weekly_pct"),
            "monthly_pct": pack.get("monthly_pct"),
            "yearly_pct": pack.get("yearly_pct"),
            "change_abs": pack.get("change_abs"),
            "weekly": pack.get("weekly") or {"pct": None, "dip": None, "zirve": None},
            "monthly": pack.get("monthly") or {"pct": None, "dip": None, "zirve": None},
            "yearly": pack.get("yearly") or {"pct": None, "dip": None, "zirve": None},
        }
        if returns.get("daily_pct") is None and quote is not None and getattr(quote, "change_pct", None) is not None:
            returns["daily_pct"] = round(float(quote.change_pct), 2)

        prev_close = pack.get("prev_close")
        day_low = pack.get("day_low")
        day_high = pack.get("day_high")
        floor_px = pack.get("floor")
        ceiling_px = pack.get("ceiling")
        market_cap = pack.get("market_cap")
        market_group = pack.get("market_group") or ("Yıldız Pazar" if company else "BIST")
        fark = returns.get("change_abs")
        if fark is None and prev_close and quote is not None:
            fark = round(float(quote.price) - float(prev_close), 2)

        # Prefer warm full-scan cache; otherwise fast lite scores (full scan can take minutes).
        decision = None
        if self._scan_cache:
            for d in self._scan_cache:
                if getattr(d, "symbol", None) == sym:
                    decision = d
                    break

        lite = None
        if decision is None:
            lite = self._overlay_signal_lite(sym, quote)

        if decision is not None:
            detail = self._serialize(decision)
        else:
            detail = {
                "symbol": sym,
                "name": (company.name if company else (getattr(quote, "name", None) or sym)),
                "sector": (company.sector if company else (getattr(quote, "sector", None) or "")),
                "price": round(float(quote.price), 4) if quote else None,
                "bid": round(float(quote.bid), 4) if quote and quote.bid else None,
                "ask": round(float(quote.ask), 4) if quote and quote.ask else None,
                "change_pct": returns.get("daily_pct"),
                "prev_close": prev_close,
                "day_low": day_low,
                "day_high": day_high,
                "floor": floor_px,
                "ceiling": ceiling_px,
                "fark": fark,
                "market_cap": market_cap,
                "market_group": market_group,
                "decision": (lite or {}).get("decision") or "NO_DATA",
                "final_decision": (lite or {}).get("final_decision") or "NO_DATA",
                "decision_label": (lite or {}).get("decision_label") or "VERİ YOK",
                "buy_score": (lite or {}).get("buy_score"),
                "sell_score": (lite or {}).get("sell_score"),
                "priority_score": (lite or {}).get("priority_score"),
                "is_favorite": is_fav,
                "watchlist_priority": fav_rec.priority if fav_rec else None,
                "signal_source": (lite or {}).get("signal_source"),
            }
        if is_fav:
            detail["is_favorite"] = True
            detail["watchlist_priority"] = fav_rec.priority if fav_rec else detail.get("watchlist_priority")
        # Merge Info-style fields onto detail even when full-scan serialize was used
        detail["prev_close"] = detail.get("prev_close") if detail.get("prev_close") is not None else prev_close
        detail["day_low"] = day_low
        detail["day_high"] = day_high
        detail["floor"] = floor_px
        detail["ceiling"] = ceiling_px
        detail["fark"] = fark
        detail["market_cap"] = market_cap
        detail["market_group"] = market_group
        if returns.get("daily_pct") is not None:
            detail["change_pct"] = returns.get("daily_pct")

        dec = str(detail.get("final_decision") or detail.get("decision") or "NO_DATA").upper()
        label_map = {
            "STRONG_BUY": "Güçlü AL",
            "BUY": "AL",
            "AL": "AL",
            "WAIT_FOR_ENTRY": "Giriş Bekle",
            "WAIT": "Bekle",
            "BEKLE": "Bekle",
            "HOLD": "Bekle",
            "WATCH": "İzle",
            "SELL": "SAT",
            "SAT": "SAT",
            "STRONG_SELL": "Güçlü SAT",
            "NO_TRADE": "İşlem Yok",
            "ALMA": "İşlem Yok",
            "NO_DATA": "VERİ YOK",
        }
        detail["decision_label"] = label_map.get(dec, detail.get("decision_label") or dec)

        score = detail.get("priority_score")
        if score is None:
            score = detail.get("buy_score")
        if score is None and detail.get("scores"):
            score = (detail.get("scores") or {}).get("final")

        kap = {
            "available": False,
            "source": "KAP",
            "items": [],
            "note": "Canlı KAP feed yok — resmi bildirim sayfasına gidin",
            "search_url": "https://www.kap.org.tr/tr/bildirim-sorgu",
            "company_url": f"https://www.kap.org.tr/tr/sirket-bilgileri/ozet/{sym}",
        }

        return {
            "ok": quote is not None or decision is not None or lite is not None,
            "symbol": sym,
            "detail": detail,
            "market": {
                "session": session_val,
                "session_label": "Piyasa açık" if session_val == "OPEN" else "Piyasa kapalı",
                "price_label": getattr(meta, "price_label", None),
                "sector": detail.get("sector") or "",
                "bid": detail.get("bid"),
                "ask": detail.get("ask"),
                "prev_close": detail.get("prev_close"),
                "day_low": day_low,
                "day_high": day_high,
                "floor": floor_px,
                "ceiling": ceiling_px,
                "fark": fark,
                "market_cap": market_cap,
                "market_group": market_group,
                "volume": getattr(quote, "volume", None) if quote else None,
            },
            "signal": {
                "decision": dec,
                "label": detail.get("decision_label"),
                "buy_score": detail.get("buy_score"),
                "sell_score": detail.get("sell_score"),
                "priority_score": detail.get("priority_score"),
                "score": score,
            },
            "favorite": {
                "is_favorite": is_fav,
                "priority": fav_rec.priority if fav_rec else None,
                "notes": fav_rec.notes if fav_rec else "",
                "score": score,
            },
            "returns": returns,
            "position": {
                "quantity": float(pos.quantity) if pos else 0,
                "avg_cost": float(pos.avg_cost) if pos else None,
            },
            "kap": kap,
            "data_source": meta.to_dict(),
            "ai_trade_plan": detail.get("ai_trade_plan"),
            "ai_forecast": detail.get("ai_forecast"),
            "note": "Sinyal ≠ emir · kazançlar gecikmeli Yahoo hesabı",
        }

    def desk_evaluate(self, symbol: str) -> dict:
        """Institutional desk evaluation for one symbol (committee + pipeline)."""
        from desk.engine import InstitutionalDeskEngine

        engine = InstitutionalDeskEngine(self)
        return engine.evaluate_symbol(symbol).to_dict()

    def desk_briefing(self) -> dict:
        """Professional daily briefing — regime, risk, opportunities."""
        from desk.engine import InstitutionalDeskEngine

        engine = InstitutionalDeskEngine(self)
        return engine.briefing()

    def desk_scan(self, *, limit: int = 20) -> list[dict]:
        """Run full desk pipeline on top scan rows."""
        from desk.engine import InstitutionalDeskEngine

        engine = InstitutionalDeskEngine(self)
        return engine.evaluate_scan(limit=limit)
