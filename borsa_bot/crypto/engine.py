"""Crypto signal engine — LIVE → validation → TA → signal → risk → trade plan.

Isolated from BIST TradingService. Paper only — no live broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from config.models import Bar, CapitalMode, QuoteSnapshot, SignalAction, utc_now
from config.settings import settings
from crypto.analytics import MIN_BARS_FULL, analyze_bars
from crypto.market import MarketType
from crypto.predictions import record_crypto_prediction
from crypto.risk_crypto import evaluate_crypto_entry, evaluate_crypto_exit
from crypto.safety import gate_crypto_provider
from crypto.signals import CryptoSignalResult, decide_crypto_signal
from crypto.symbols import normalize_crypto_app_symbol
from crypto.trade_plan_crypto import build_crypto_trade_plan
from data.contract import validate_canonical_quote
from data.integrity import DataSourceKind
from data.validation import MarketDataGateCode
from portfolio.ledger import PortfolioLedger
from prediction.store import PredictionStore
from risk.engine import RiskEngine


def _synthetic_live_bars(
    *,
    symbol: str,
    n: int = 240,
    start_price: float = 100.0,
    provider: str = "paribu",
) -> list[Bar]:
    """Test helper factory — LIVE-tagged deterministic bars (not for production fill)."""
    now = datetime.now(timezone.utc)
    bars: list[Bar] = []
    px = start_price
    for i in range(n):
        drift = 0.001 if (i % 17) > 8 else -0.0007
        o = px
        c = max(0.01, o * (1 + drift))
        h = max(o, c) * 1.002
        l = min(o, c) * 0.998
        bars.append(
            Bar(
                ts=now - timedelta(minutes=15 * (n - i)),
                open=round(o, 6),
                high=round(h, 6),
                low=round(l, 6),
                close=round(c, 6),
                volume=1_000 + i * 3,
                trades=10,
                data_source_kind=DataSourceKind.LIVE.value,
                symbol=symbol,
                timeframe="15m",
                provider=provider,
                environment_origin="LIVE",
            )
        )
        px = c
    return bars


@dataclass
class CryptoSignalEngine:
    provider: Any  # Paribu or public CEX (okx/gate/kraken failover)
    ledger: PortfolioLedger | None = None
    risk: RiskEngine | None = None
    predictions: PredictionStore | None = None
    max_symbols: int = 40
    record_predictions: bool = True
    _last_gate: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ledger is None:
            # Isolated paper ledger path for crypto sizing (does not touch BIST scan)
            self.ledger = PortfolioLedger(db_path=settings.db_path)
        if self.risk is None:
            self.risk = RiskEngine(self.ledger)
        if self.predictions is None:
            self.predictions = PredictionStore()

    def gate(self) -> Any:
        g = gate_crypto_provider(
            self.provider,
            app_env=settings.app_env,
            crypto_enabled=settings.crypto_enabled,
        )
        self._last_gate = g.to_dict()
        return g

    def analyze_symbol(
        self,
        symbol: str,
        *,
        bars: Sequence[Bar] | None = None,
        quote: QuoteSnapshot | None = None,
    ) -> CryptoSignalResult:
        """Full pipeline for one symbol. Stale/invalid → NO_SIGNAL."""
        sym = normalize_crypto_app_symbol(symbol)
        empty = CryptoSignalResult(symbol=sym, signal=SignalAction.NO_TRADE.value, note="init")

        if not settings.crypto_enabled or not settings.crypto_signals_enabled:
            empty.note = "CRYPTO_SIGNALS_DISABLED"
            return empty

        g = self.gate()
        if not g.ok or not self.provider.has_market_data():
            empty.note = f"NO_LIVE_DATA:{g.code.value}"
            return empty

        try:
            q = quote or self.provider.get_quote(sym)
        except Exception as exc:  # noqa: BLE001
            empty.note = f"NO_QUOTE:{exc}"
            return empty

        # Freshness / canonical validation
        max_age = settings.data_freshness_sec
        cc = validate_canonical_quote(q, max_age_sec=max_age)
        if not cc.ok:
            empty.note = f"VALIDATION:{cc.quality.value}:{cc.note}"
            return empty
        if q.data_source_kind not in {DataSourceKind.LIVE.value, "LIVE"}:
            empty.note = f"NON_LIVE_SOURCE:{q.data_source_kind}"
            return empty

        bars_15 = list(bars) if bars is not None else list(self.provider.get_bars(sym, lookback=MIN_BARS_FULL + 20))
        tech = analyze_bars(sym, bars_15, q)
        if not tech.ok:
            empty.note = tech.note
            empty.mtf = tech.mtf
            empty.model_score = tech.model_score
            empty.model_score_definition = tech.model_score_definition
            return empty

        assert tech.indicators is not None
        owned = self.ledger.get_position(sym) is not None
        plan_view = build_crypto_trade_plan(
            price=q.price,
            ind=tech.indicators,
            equity=self.ledger.equity(),
            cash=self.ledger.cash,
            size_mult=1.0,
            max_exposure_pct=settings.crypto_max_exposure_pct,
        )

        prelim = decide_crypto_signal(
            tech,
            plan=plan_view,
            risk=None,
            price=q.price,
            owned=owned,
            capital_mode=self.risk.capital_mode,
            portfolio_dd_pct=self.ledger.drawdown_pct(),
        )
        try:
            action = SignalAction(prelim.signal)
        except ValueError:
            action = SignalAction.WAIT

        from profit.ev import compute_opportunity, dynamic_size_multiplier

        opp = None
        size_mult = 1.0
        if plan_view and tech.scores and tech.indicators:
            opp = compute_opportunity(
                scores=tech.scores,
                plan=plan_view.to_legacy(),
                price=q.price,
                ind=tech.indicators,
                regime=tech.regime,
                conflict=tech.mtf_conflict,
                mtf_aligned=tech.mtf_aligned,
                portfolio_dd_pct=self.ledger.drawdown_pct(),
            )
            if opp:
                size_mult = dynamic_size_multiplier(
                    opp, capital_mode=self.risk.capital_mode, regime=tech.regime
                )

        if action in {SignalAction.BUY, SignalAction.STRONG_BUY, SignalAction.AL}:
            spread = None
            if hasattr(self.provider, "quote_spread_pct"):
                spread = self.provider.quote_spread_pct(q)
            elif q.bid > 0 and q.ask > 0 and q.ask >= q.bid:
                from data.contract import compute_spread_pct

                spread = compute_spread_pct(q.bid, q.ask)
            risk_res = evaluate_crypto_entry(
                self.risk,
                symbol=sym,
                price=q.price,
                ind=tech.indicators,
                action=action,
                plan=plan_view.to_legacy() if plan_view else None,
                spread_pct=spread,
                opportunity=opp,
                size_mult=size_mult,
                max_exposure_pct=settings.crypto_max_exposure_pct,
                atr_cap_pct=settings.crypto_atr_cap_pct,
            )
        elif action in {SignalAction.SELL, SignalAction.STRONG_SELL, SignalAction.SAT}:
            risk_res = evaluate_crypto_exit(self.risk, action)
        else:
            risk_res = None

        final = decide_crypto_signal(
            tech,
            plan=plan_view,
            risk=risk_res,
            price=q.price,
            owned=owned,
            capital_mode=self.risk.capital_mode,
            portfolio_dd_pct=self.ledger.drawdown_pct(),
        )
        final.provider = getattr(self.provider, "provider_id", "paribu")
        final.data_source_kind = q.data_source_kind

        if self.record_predictions and settings.crypto_predictions_enabled:
            try:
                pid = record_crypto_prediction(self.predictions, final, price=q.price)
                if pid:
                    final.note = f"{final.note};prediction_id={pid}"
            except Exception:  # noqa: BLE001
                pass
        return final

    def scan(self, symbols: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Scan crypto universe (capped). Returns signal dicts only — no broker submit."""
        if not settings.crypto_enabled or not settings.crypto_signals_enabled:
            return []
        g = self.gate()
        if not g.ok:
            return []
        if symbols is None:
            symbols = self.provider.list_symbols()[: self.max_symbols]
        out: list[dict[str, Any]] = []
        for sym in symbols:
            try:
                res = self.analyze_symbol(sym)
                out.append(res.to_dict())
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {
                        "symbol": normalize_crypto_app_symbol(sym),
                        "market_type": MarketType.CRYPTO.value,
                        "signal": SignalAction.NO_TRADE.value,
                        "note": f"ERROR:{exc}",
                        "paper_only": True,
                    }
                )
        return out
