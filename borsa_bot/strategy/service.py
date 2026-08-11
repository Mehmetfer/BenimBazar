from __future__ import annotations

from dataclasses import asdict

from ai.quality import assess_signal_quality
from config.models import OrderRequest, RiskLevel, SignalAction, SymbolDecision
from config.settings import settings
from data.providers import MarketDataProvider, create_provider
from execution.paper import PaperBroker
from execution.safety import SafetyGate
from indicators.engine import compute_indicators
from portfolio.ledger import PortfolioLedger
from risk.engine import RiskEngine
from strategy.regime import detect_regime, trend_label
from strategy.signal_engine import build_explanation, decide_action, score_buy, score_sell
from strategy.modules import ensemble_votes


class TradingService:
    def __init__(self) -> None:
        self.provider: MarketDataProvider = create_provider(settings.data_provider)
        self.ledger = PortfolioLedger()
        self.risk = RiskEngine(self.ledger)
        self.broker = PaperBroker(self.ledger)
        self.safety = SafetyGate()
        self.system_status = "OK"
        self.last_error = ""

    def health(self) -> dict:
        fresh = self.provider.is_fresh(60)
        ok, reason = self.safety.evaluate(
            data_fresh=fresh,
            api_ok=True,
            order_status_ok=True,
            spread_pct=0.0,
            daily_loss_pct=self.ledger.daily_loss_pct(),
            clock_ok=True,
        )
        if settings.kill_switch:
            status = "KILL_SWITCH"
        elif not ok:
            status = reason
        elif not fresh:
            status = "STALE_DATA"
        else:
            status = self.system_status
        live_ok, live_failed = self.risk.preflight_live(
            data_fresh=fresh, api_ok=True, market_open=True
        )
        return {
            "status": status,
            "mode": settings.mode,
            "data_fresh": fresh,
            "kill_switch": settings.kill_switch,
            "safety_ok": ok,
            "live_preflight_ok": live_ok,
            "live_preflight_failed": live_failed,
            "error": self.last_error,
        }

    def tick(self) -> None:
        self.provider.tick()

    def scan(self) -> list[SymbolDecision]:
        self.tick()
        regime = detect_regime(self.provider)
        index_bars = self.provider.get_bars("XU100", 220)
        index_ind = compute_indicators(index_bars)
        index_bullish = bool(index_ind and index_ind.ema21 > index_ind.ema50)

        marks = {}
        decisions: list[SymbolDecision] = []
        for symbol in self.provider.list_symbols():
            quote = self.provider.get_quote(symbol)
            marks[symbol] = quote.price
            bars = self.provider.get_bars(symbol, 220)
            ind = compute_indicators(bars)
            if ind is None:
                continue
            owned = self.ledger.get_position(symbol) is not None
            buy = score_buy(ind, quote.price, quote.volume, regime, index_bullish)
            sell = score_sell(ind, quote.price, quote.volume, owned)
            action = decide_action(buy, sell, owned, regime)
            votes = ensemble_votes(ind, quote.price, quote.volume)
            ai_conf, ai_notes = assess_signal_quality(
                action=action,
                buy_score=buy,
                sell_score=sell,
                ind=ind,
                regime=regime,
                spread_pct=quote.spread_pct,
            )
            stop = round(quote.price - ind.atr14 * settings.atr_stop_mult, 2)
            target = round(quote.price + ind.atr14 * settings.atr_take_mult, 2)
            risk = RiskLevel.LOW
            if action == SignalAction.AL:
                rd = self.risk.evaluate_entry(
                    symbol=symbol,
                    sector=quote.sector,
                    price=quote.price,
                    ind=ind,
                    action=action,
                )
                risk = rd.risk
                if not rd.allowed:
                    action = SignalAction.BEKLE
                    stop, target = rd.stop_price, rd.target_price
            explanation = build_explanation(action, buy, sell, ind, votes, regime) + f"; ai={ai_notes}"
            d = SymbolDecision(
                symbol=symbol,
                name=quote.name,
                sector=quote.sector,
                price=quote.price,
                trend=trend_label(ind),
                buy_score=buy,
                sell_score=sell,
                ai_confidence=ai_conf,
                risk=risk,
                signal=action,
                regime=regime,
                stop_price=stop,
                target_price=target,
                explanation=explanation,
                indicators={
                    "rsi": round(ind.rsi14, 2),
                    "atr": round(ind.atr14, 2),
                    "adx": round(ind.adx14, 2),
                    "ema9": round(ind.ema9, 2),
                    "ema21": round(ind.ema21, 2),
                    "ema50": round(ind.ema50, 2),
                    "ema200": round(ind.ema200, 2),
                },
                strategy_votes=votes,
            )
            decisions.append(d)
            self.ledger.log_decision(
                {
                    "symbol": d.symbol,
                    "price": d.price,
                    "signal": d.signal.value,
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
        # Sort actionable first
        order = {SignalAction.AL: 0, SignalAction.SAT: 1, SignalAction.BEKLE: 2, SignalAction.ALMA: 3}
        decisions.sort(key=lambda x: (order[x.signal], -x.buy_score))
        return decisions

    def dashboard(self) -> dict:
        decisions = self.scan()
        health = self.health()
        return {
            "health": health,
            "portfolio": {
                "equity": round(self.ledger.equity(), 2),
                "cash": round(self.ledger.cash, 2),
                "daily_pnl": round(self.ledger.daily_pnl(), 2),
                "total_pnl": round(self.ledger.total_pnl(), 2),
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
                "AL": [asdict(d) for d in decisions if d.signal == SignalAction.AL],
                "SAT": [asdict(d) for d in decisions if d.signal == SignalAction.SAT],
                "BEKLE": [asdict(d) for d in decisions if d.signal == SignalAction.BEKLE],
                "ALMA": [asdict(d) for d in decisions if d.signal == SignalAction.ALMA],
            },
            "universe": [
                {
                    "symbol": d.symbol,
                    "name": d.name,
                    "price": d.price,
                    "trend": d.trend,
                    "buy_score": d.buy_score,
                    "sell_score": d.sell_score,
                    "ai_confidence": d.ai_confidence,
                    "risk": d.risk.value,
                    "signal": d.signal.value,
                    "regime": d.regime.value,
                    "explanation": d.explanation,
                    "stop_price": d.stop_price,
                    "target_price": d.target_price,
                }
                for d in decisions
            ],
        }

    def execute_signal(self, symbol: str) -> dict:
        if settings.is_live:
            return {"ok": False, "message": "LIVE mode blocked"}
        quote = self.provider.get_quote(symbol)
        ok, reason = self.safety.evaluate(
            data_fresh=self.provider.is_fresh(60),
            api_ok=True,
            order_status_ok=True,
            spread_pct=quote.spread_pct,
            daily_loss_pct=self.ledger.daily_loss_pct(),
            clock_ok=True,
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
            rd = self.risk.evaluate_entry(
                symbol=symbol, sector=quote.sector, price=quote.price, ind=ind, action=d.signal
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
            return {"ok": result.ok, "result": asdict(result)}
        if d.signal == SignalAction.SAT:
            rd = self.risk.evaluate_exit(symbol, d.signal)
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
            return {"ok": result.ok, "result": asdict(result)}
        return {"ok": False, "message": f"no actionable signal ({d.signal.value})"}
