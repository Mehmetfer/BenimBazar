from __future__ import annotations

from dataclasses import asdict

from ai.calibration import CalibrationMonitor
from ai.ensemble import build_specialists, meta_decision
from config.models import MarketRegime, SignalAction
from config.settings import settings
from data.providers import MarketDataProvider
from engines.day_trading import evaluate_day
from engines.long_term import HorizonOpportunity, evaluate_long_term
from engines.mode_selector import select_modes
from engines.swing import evaluate_swing
from factors.engine import compute_factors
from fundamental.provider import get_fundamentals, score_fundamentals
from indicators.engine import compute_indicators
from market_regime.engine import detect_regime
from news.analyzer import classify_headline, latest_stub_headline, score_news
from portfolio.sleeves import allocate_sleeves
from portfolio.stress import portfolio_risk_report
from risk.day_limits import DayTradingRiskState
from signals.engine import market_score, technical_score, volume_score
from technical.mtf import analyze_mtf, mtf_conflict_risk
from technical.price_action import analyze_price_action
from technical.sector import liquidity_score, sector_relative_strength
from universe.engine import select_universe


def _ser_opp(o: HorizonOpportunity) -> dict:
    d = asdict(o)
    d["decision"] = o.decision.value
    return d


class MultiHorizonOrchestrator:
    """Runs LONG / SWING / DAY engines separately; does not mix capital sleeves."""

    def __init__(self, provider: MarketDataProvider, equity: float = 100_000.0) -> None:
        self.provider = provider
        self.equity = equity
        self.day_risk = DayTradingRiskState()
        self.calibration = CalibrationMonitor()

    def run(self) -> dict:
        self.provider.tick()
        regime = detect_regime(self.provider)
        mode = select_modes(self.provider, regime)
        sleeves = allocate_sleeves(self.equity, mode)
        self.day_risk.evaluate(equity=self.equity, open_day_exposure=0.0)

        index_ind = compute_indicators(self.provider.get_bars("XU100", 220))
        index_bullish = bool(index_ind and index_ind.ema21 > index_ind.ema50)
        universe = {m.symbol: m for m in select_universe(self.provider)}

        long_ops: list[HorizonOpportunity] = []
        swing_ops: list[HorizonOpportunity] = []
        day_ops: list[HorizonOpportunity] = []
        meta_rows = []

        for symbol in self.provider.list_symbols():
            uni = universe.get(symbol)
            if uni and not uni.eligible and mode.primary.value == "DAY_TRADING":
                continue
            quote = self.provider.get_quote(symbol)
            bars = self.provider.get_bars(symbol, 240)
            ind = compute_indicators(bars)
            if ind is None:
                continue
            closes = [b.close for b in bars]
            xu = self.provider.get_bars("XU100", 40)
            xu_c = [b.close for b in xu]
            rs_idx = 0.0
            if len(closes) > 20 and len(xu_c) > 20 and xu_c[-20]:
                rs_idx = (closes[-1] / closes[-20] - 1) - (xu_c[-1] / xu_c[-20] - 1)
            factors = compute_factors(symbol, closes, ind, quote.price, rs_idx)
            _, sector_sc, _ = sector_relative_strength(self.provider, symbol, quote.sector)
            mtf = analyze_mtf(bars, 15)
            conflict, _, _ = mtf_conflict_risk(mtf)
            pa = analyze_price_action(bars, ind, quote.volume)
            tech, _ = technical_score(ind, quote.price)
            fund, _ = score_fundamentals(get_fundamentals(symbol))
            vol_s, _ = volume_score(ind, quote.volume)
            news = classify_headline(symbol, latest_stub_headline(symbol))
            news_sc, _, news_block = score_news(news)
            liq, _ = liquidity_score(quote, ind)
            mkt = market_score(regime, index_bullish)
            anomaly = 25 if (uni and uni.pump_dump_flag) else 0
            anomaly += 20 if pa.false_breakout else 0
            anomaly += 15 if news_block else 0

            lt = evaluate_long_term(
                symbol=symbol, price=quote.price, ind=ind, factors=factors,
                sector_score=sector_sc, regime=regime, scores_final=tech, conflict=conflict,
            )
            sw = evaluate_swing(
                symbol=symbol, price=quote.price, ind=ind, factors=factors, sector_score=sector_sc,
                regime=regime, mtf=mtf, pa=pa, conflict=conflict, volume_score=vol_s,
            )
            day = evaluate_day(
                symbol=symbol, quote=quote, ind=ind, regime=regime, vol_regime=mode.volatility,
                pa=pa, mtf=mtf, index_bullish=index_bullish, conflict=conflict or news_block,
                day_paused=self.day_risk.paused or mode.primary.value == "NO_TRADE",
            )
            # De-prioritize engines not in mode list (still computed for transparency)
            if Horizon_disabled(mode, "LONG_TERM"):
                if lt.decision in {SignalAction.BUY, SignalAction.STRONG_BUY}:
                    lt.decision = SignalAction.WATCH
            if Horizon_disabled(mode, "SWING"):
                if sw.decision in {SignalAction.BUY, SignalAction.STRONG_BUY}:
                    sw.decision = SignalAction.WATCH
            if Horizon_disabled(mode, "DAY_TRADING") or mode.primary.value == "NO_TRADE":
                day.decision = SignalAction.NO_TRADE

            lt.confidence = self.calibration.adjust(lt.confidence)
            sw.confidence = self.calibration.adjust(sw.confidence)
            day.confidence = self.calibration.adjust(day.confidence)

            long_ops.append(lt)
            swing_ops.append(sw)
            day_ops.append(day)

            specs = build_specialists(
                technical=tech,
                fundamental=0.5 * fund + 0.5 * factors.quality,
                momentum=factors.momentum,
                value=factors.value,
                quality=factors.quality,
                news=news_sc,
                market=mkt,
                risk_safety=liq,
                anomaly_penalty=anomaly,
            )
            meta_dec, meta_score, meta_why = meta_decision(specs, regime=regime, horizon_ops=[lt, sw, day])
            meta_rows.append(
                {
                    "symbol": symbol,
                    "meta_decision": meta_dec.value,
                    "meta_score": meta_score,
                    "meta_why": meta_why,
                    "specialists": specs.as_dict(),
                    "long_term": _ser_opp(lt),
                    "swing": _ser_opp(sw),
                    "day_trading": _ser_opp(day),
                    "universe_ok": uni.eligible if uni else True,
                }
            )

        def top(ops: list[HorizonOpportunity], n: int = 10):
            ranked = sorted(
                ops,
                key=lambda o: (o.expected_value * 10 + o.confidence * 0.3 + o.win_probability * 20 - (0 if o.decision in {SignalAction.BUY, SignalAction.STRONG_BUY} else 30)),
                reverse=True,
            )
            return [_ser_opp(o) for o in ranked[:n]]

        # Stress on empty book by default (positions filled by caller)
        risk_stats = portfolio_risk_report([], returns=[-0.01, 0.005, -0.02, 0.01, -0.015, 0.008] * 5, equity=self.equity)

        return {
            "mode": {
                "market": mode.market.value,
                "volatility": mode.volatility.value,
                "trend": mode.trend.value,
                "primary": mode.primary.value,
                "priorities": [h.value for h in mode.priorities],
                "reason": mode.reason,
                "cash_bias": mode.cash_bias,
            },
            "sleeves": sleeves.as_dict(),
            "day_risk": {
                "paused": self.day_risk.paused,
                "pause_reason": self.day_risk.pause_reason,
                "trades_today": self.day_risk.trades_today,
                "limits": {
                    "max_daily_loss_pct": settings.day_max_daily_loss_pct,
                    "max_trades": settings.day_max_trades,
                    "max_consecutive_losses": settings.day_max_consecutive_losses,
                },
            },
            "top": {
                "LONG_TERM": top(long_ops),
                "SWING": top(swing_ops),
                "DAY_TRADING": top(day_ops),
            },
            "universe_meta": meta_rows,
            "portfolio_risk": {
                "var_95": risk_stats.var_95,
                "cvar_95": risk_stats.cvar_95,
                "stress": [s.__dict__ for s in risk_stats.stress],
                "note": risk_stats.note,
            },
            "calibration": self.calibration.report(),
            "philosophy": (
                "SCAN AGGRESSIVELY · FILTER AGGRESSIVELY · TRADE SELECTIVELY. "
                "Engines are separate. NO TRADE is valid. No profit guarantee. LIVE OFF."
            ),
            "live": False,
        }


def Horizon_disabled(mode, name: str) -> bool:
    return name not in [h.value for h in mode.priorities] or mode.primary.value == "NO_TRADE" and name == "DAY_TRADING"
