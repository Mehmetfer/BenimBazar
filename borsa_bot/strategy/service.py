from __future__ import annotations

from dataclasses import asdict

from ai.quality import assess_signal_quality, classify_volatility_regime
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
from fundamental.provider import get_fundamentals, score_fundamentals
from indicators.engine import compute_indicators
from market_regime.engine import detect_regime, trend_label
from news.analyzer import classify_headline, latest_stub_headline, score_news
from portfolio.ledger import PortfolioLedger
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
from strategy.modules import ensemble_votes, regime_weights, weighted_ensemble_bias
from strategy.ranking import example_ranking_report
from technical.mtf import analyze_mtf, mtf_conflict_risk
from technical.sector import liquidity_score, sector_relative_strength


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
        self.system_status = "OK"
        self.last_error = ""
        self.pending_approvals: dict[str, dict] = {}
        self.capital_mode = CapitalMode.NORMAL

    def health(self) -> dict:
        fresh = self.provider.is_fresh(60)
        ok, reason = self.safety.evaluate(
            data_fresh=fresh,
            api_ok=True,
            order_status_ok=True,
            spread_pct=0.0,
            daily_loss_pct=self.ledger.daily_loss_pct(),
            clock_ok=True,
            max_spread_pct=settings.max_spread_pct,
        )
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
            data_fresh=fresh, api_ok=True, market_open=True
        )
        return {
            "status": status,
            "mode": settings.mode,
            "capital_mode": self.capital_mode.value,
            "data_fresh": fresh,
            "kill_switch": settings.kill_switch,
            "paused": self.risk.paused,
            "safety_ok": ok,
            "live_preflight_ok": live_ok,
            "live_preflight_failed": live_failed,
            "manual_approval": settings.require_manual_approval,
            "error": self.last_error,
            "objectives": SYSTEM_OBJECTIVES,
            "philosophy": (
                "Sermaye koruma → risk kontrolü → yüksek olasılıklı fırsat → "
                "risk-ayarlı getiri. NO_TRADE birinci sınıf. AI emir vermez. "
                "Kâr garantisi yok; paper trading LIVE öncesi zorunlu."
            ),
            "strategy_ranking_example": example_ranking_report(),
        }

    def tick(self) -> None:
        self.provider.tick()

    def scan(self) -> list[SymbolDecision]:
        self.tick()
        regime = detect_regime(self.provider)
        index_bars = self.provider.get_bars("XU100", 220)
        index_ind = compute_indicators(index_bars)
        index_bullish = bool(index_ind and index_ind.ema21 > index_ind.ema50)
        atr_index_pct = (index_ind.atr14 / index_ind.ema21 * 100) if index_ind and index_ind.ema21 else 2.0
        weights = regime_weights(regime)

        marks = {}
        decisions: list[SymbolDecision] = []
        # Capital mode from portfolio + market (recomputed each scan)
        self.capital_mode = select_capital_mode(
            self.ledger,
            regime=regime,
            atr_index_pct=atr_index_pct,
            liquidity_ok=True,
        )
        self.risk.capital_mode = self.capital_mode

        for symbol in self.provider.list_symbols():
            quote = self.provider.get_quote(symbol)
            marks[symbol] = quote.price
            bars = self.provider.get_bars(symbol, 240)
            ind = compute_indicators(bars)
            if ind is None:
                continue
            owned = self.ledger.get_position(symbol) is not None
            mtf = analyze_mtf(bars, base_tf_minutes=15)
            mtf_conflict, mtf_penalty, mtf_note = mtf_conflict_risk(mtf)
            mtf_aligned = (not mtf_conflict) and sum(1 for v in mtf.values() if v == "BULL") >= 3
            rs, sector_sc, sector_notes = sector_relative_strength(self.provider, symbol, quote.sector)
            liq, liq_notes = liquidity_score(quote, ind)
            news = classify_headline(symbol, latest_stub_headline(symbol))
            news_sc, news_notes, news_block = score_news(news)
            tech, tech_reasons = technical_score(ind, quote.price)
            fund, fund_notes = score_fundamentals(get_fundamentals(symbol))
            mom = momentum_score(ind)
            vol, vol_notes = volume_score(ind, quote.volume)
            mkt = market_score(regime, index_bullish)
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
            bundle = ScoreBundle(
                technical=round(tech, 1),
                fundamental=round(fund, 1),
                market=round(mkt, 1),
                sector=round(sector_sc, 1),
                momentum=round(mom, 1),
                volume=round(vol, 1),
                news=round(news_sc, 1),
                liquidity=round(liq, 1),
                risk=round(max(0, 100 - safety), 1),
                ai_confidence=round(ai_conf, 1),
                final=0.0,
            )
            votes = ensemble_votes(ind, quote.price, quote.volume)
            bias = weighted_ensemble_bias(votes, weights)
            final = (
                bundle.technical * 0.25
                + bundle.fundamental * 0.10
                + bundle.market * 0.15
                + bundle.sector * 0.12
                + bundle.momentum * 0.10
                + bundle.volume * 0.10
                + bundle.news * 0.05
                + bundle.liquidity * 0.08
                + (100 - bundle.risk) * 0.05
            )
            final = final * 0.9 + ai_conf * 0.1
            final += max(-5, min(5, bias))  # soft regime-weighted ensemble nudge
            if regime == MarketRegime.STRONG_BEAR:
                final *= 0.75
            elif regime == MarketRegime.BEAR:
                final *= 0.85
            if mtf_conflict:
                final *= 0.8
            bundle.final = round(max(0, min(100, final)), 1)

            conflict, conflict_why = detect_conflict(bundle, bundle.risk >= 55)
            if mtf_conflict:
                conflict = True
                conflict_why = conflict_why or mtf_note

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
            reasons.append(f"capital_mode={self.capital_mode.value}")
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
            if mtf_note:
                risks.append(mtf_note)

            stop = plan.stop if plan else None
            target = plan.target1 if plan else None
            risk_level = RiskLevel.LOW
            if signal in ENTRY_ACTIONS:
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
                if not rd.allowed:
                    decision = SignalAction.NO_TRADE if rd.reason.startswith(("KILL", "capital", "negative")) else SignalAction.WAIT
                    signal = _to_exec_signal(decision)
                    reasons.append(f"RiskEngine veto: {rd.reason}")
                    stop, target = rd.stop_price, rd.target_price
                elif plan:
                    plan.quantity = rd.quantity

            explanation = (
                f"DECISION={decision.value} FINAL={bundle.final:.0f} EV={(opp.expected_value if opp else 0):.3f} "
                f"Pwin={(opp.p_win if opp else 0):.2f} MODE={self.capital_mode.value}; "
                f"reasons={'; '.join(reasons[:6])}; risks={'; '.join(risks) or 'n/a'}"
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
            )
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
        order = {
            SignalAction.AL: 0,
            SignalAction.SAT: 1,
            SignalAction.BEKLE: 2,
            SignalAction.ALMA: 3,
        }
        decisions.sort(key=lambda x: (order.get(x.signal, 9), -x.buy_score))
        return decisions

    def dashboard(self) -> dict:
        decisions = self.scan()
        health = self.health()
        sector_exp: dict[str, int] = {}
        for p in self.ledger.positions():
            sector_exp[p.sector] = sector_exp.get(p.sector, 0) + 1

        def bucket(name: str):
            return [self._serialize(d) for d in decisions if d.decision.value == name or d.signal.value == name]

        return {
            "health": health,
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
            "universe": [self._serialize(d) for d in decisions],
        }

    def _serialize(self, d: SymbolDecision) -> dict:
        base = {
            "symbol": d.symbol,
            "name": d.name,
            "sector": d.sector,
            "price": d.price,
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
        }
        if d.scores:
            base["scores"] = asdict(d.scores)
        if d.trade_plan:
            base["trade_plan"] = asdict(d.trade_plan)
        if d.opportunity:
            base["opportunity"] = asdict(d.opportunity)
        return base

    def execute_signal(self, symbol: str, approved: bool = False) -> dict:
        if settings.is_live:
            return {"ok": False, "message": "LIVE mode blocked — paper trading zorunlu"}
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
            return {"ok": result.ok, "result": asdict(result)}
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
            return {"ok": result.ok, "result": asdict(result)}
        return {"ok": False, "message": f"no actionable signal ({d.decision.value})"}
