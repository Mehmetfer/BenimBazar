"""Crypto foundation service — isolated from TradingService (BIST).

Phase 3–4: signal scan + dashboard/UI projection (paper only).
Live broker still disabled — paper analysis only.
"""

from __future__ import annotations

from typing import Any

from config.settings import settings
from crypto.alerts import emit_crypto_signal_alerts
from crypto.backfill import backfill_symbol
from crypto.chart import SUPPORTED_TF, bars_to_chart, normalize_timeframe
from crypto.dashboard import (
    card_from_parts,
    live_status_badge,
    sectionize,
    sort_dashboard_rows,
)
from crypto.engine import CryptoSignalEngine
from crypto.market import MarketType
from crypto.providers.factory import create_crypto_provider, is_live_crypto_provider
from crypto.providers.paribu import RequiredCryptoProvider
from crypto.safety import gate_crypto_provider
from crypto.symbols import normalize_crypto_app_symbol, to_display_symbol
from data.validation import normalize_app_env


class CryptoFoundationService:
    """CRYPTO market plane entrypoint. BIST TradingService remains untouched."""

    def __init__(self, favorites: Any = None, alerts: Any = None) -> None:
        self.provider = create_crypto_provider()
        self.market_type = MarketType.CRYPTO
        self._gate = None
        self._engine: CryptoSignalEngine | None = None
        self.favorites = favorites
        self.alerts = alerts
        self._emit_signal_alerts = True

    def bind_shared(self, *, favorites: Any, alerts: Any) -> None:
        """Share FavoritesStore + AlertManager with BIST TradingService (same user prefs)."""
        self.favorites = favorites
        self.alerts = alerts

    def refresh_provider(self) -> None:
        old = self.provider
        self.provider = create_crypto_provider()
        self._engine = None
        close = getattr(old, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    def _signal_engine(self) -> CryptoSignalEngine | None:
        if not is_live_crypto_provider(self.provider) or isinstance(self.provider, RequiredCryptoProvider):
            return None
        if not self.provider.has_market_data():
            return None
        if self._engine is None:
            self._engine = CryptoSignalEngine(
                provider=self.provider,
                max_symbols=settings.crypto_scan_max_symbols,
                record_predictions=settings.crypto_predictions_enabled,
            )
        return self._engine

    def status(self) -> dict[str, Any]:
        gate = gate_crypto_provider(
            self.provider,
            app_env=settings.app_env,
            crypto_enabled=settings.crypto_enabled,
        )
        self._gate = gate
        meta = self.provider.source_meta(settings.data_freshness_sec)
        provenance = getattr(self.provider, "provenance", lambda: {})()
        symbols = list(self.provider.list_symbols()) if settings.crypto_enabled else []
        sample_quotes: list[dict[str, Any]] = []
        if is_live_crypto_provider(self.provider) and self.provider.has_market_data():
            for sym in symbols[:5]:
                try:
                    q = self.provider.get_quote(sym)
                    sample_quotes.append(
                        {
                            "symbol": q.symbol,
                            "display": q.name,
                            "price": q.price,
                            "bid": q.bid,
                            "ask": q.ask,
                            "spread_pct": q.spread_pct,
                            "volume": q.volume,
                            "ts": q.ts.isoformat() if q.ts else None,
                            "market_type": MarketType.CRYPTO.value,
                            "data_source_kind": q.data_source_kind,
                            "provider": q.provider,
                            "market_status": q.market_status,
                            "live_status": live_status_badge(
                                has_quote=True,
                                data_source_kind=q.data_source_kind,
                                ts=q.ts,
                            ),
                        }
                    )
                except Exception:  # noqa: BLE001
                    continue
        return {
            "market_type": MarketType.CRYPTO.value,
            "crypto_enabled": settings.crypto_enabled,
            "paribu_enabled": settings.paribu_enabled,
            "crypto_signals_enabled": settings.crypto_signals_enabled,
            "crypto_provider": settings.crypto_provider,
            "crypto_failover": getattr(settings, "crypto_failover", ""),
            "provider_id": getattr(self.provider, "provider_id", ""),
            "provider_class": type(self.provider).__name__,
            "is_stub": bool(getattr(self.provider, "is_stub", False)),
            "is_real_provider": bool(getattr(self.provider, "is_real_provider", False)),
            "has_market_data": bool(self.provider.has_market_data()),
            "signals_allowed": bool(gate.signals_allowed),
            "tradeable": False,
            "live_trading": False,
            "paper_only": True,
            "data_source": meta.to_dict(),
            "provenance": provenance,
            "gate": gate.to_dict(),
            "symbols": symbols,
            "symbol_count": len(symbols),
            "sample_quotes": sample_quotes,
            "websocket": (getattr(self.provider, "status_dict", lambda: {})() or {}).get("websocket"),
            "ui": {
                "title": "Kripto (Paribu)",
                "ready": bool(self.provider.has_market_data()),
                "message": (
                    f"Paribu LIVE · {len(symbols)} markets · signals={'ON' if gate.signals_allowed else 'OFF'} · PAPER ONLY · BIST etkilenmez"
                    if self.provider.has_market_data()
                    else (
                        "CRYPTO_ENABLED=false — kripto piyasası kapalı"
                        if not settings.crypto_enabled
                        else "Paribu bağlı değil veya veri yok"
                    )
                ),
            },
            "app_env": normalize_app_env(settings.app_env).value,
            "docs": "crypto/docs/PARIBU_API.md",
        }

    def health(self) -> dict[str, Any]:
        """Ops health — Paribu connection, discovery, freshness, OHLCV readiness."""
        gate = gate_crypto_provider(
            self.provider,
            app_env=settings.app_env,
            crypto_enabled=settings.crypto_enabled,
        )
        base = getattr(self.provider, "health_dict", lambda: {})()
        return {
            **base,
            "crypto_enabled": settings.crypto_enabled,
            "paribu_enabled": settings.paribu_enabled,
            "crypto_signals_enabled": settings.crypto_signals_enabled,
            "gate": gate.to_dict(),
            "provider_class": type(self.provider).__name__,
            "mock_fallback": False,
            "paper_only": True,
            "live_orders": False,
        }

    def markets(self) -> dict[str, Any]:
        """Full discovered market catalog (not hardcoded BTC/ETH/SOL)."""
        if not settings.crypto_enabled:
            return {
                "ok": False,
                "market_type": "CRYPTO",
                "count": 0,
                "markets": [],
                "note": "CRYPTO_ENABLED=false",
            }
        fn = getattr(self.provider, "list_markets", None)
        if not callable(fn):
            return {
                "ok": False,
                "market_type": "CRYPTO",
                "count": 0,
                "markets": [],
                "note": "provider has no list_markets",
            }
        try:
            if not self.provider.has_market_data():
                self.provider.tick()
        except Exception:  # noqa: BLE001
            pass
        rows = [m.to_dict() for m in fn()]
        return {
            "ok": bool(rows),
            "market_type": "CRYPTO",
            "provider": getattr(self.provider, "provider_id", ""),
            "count": len(rows),
            "markets": rows,
            "hardcoded": False,
            "note": "Discovered from GET /market/ticker — precision fields UNKNOWN until API exposes them",
        }

    def scan(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        """Crypto signal scan — empty unless CRYPTO_SIGNALS_ENABLED + live MD."""
        eng = self._signal_engine()
        if eng is None:
            return []
        return eng.scan(symbols)

    def signal(self, symbol: str) -> dict[str, Any]:
        eng = self._signal_engine()
        if eng is None:
            return {
                "symbol": normalize_crypto_app_symbol(symbol),
                "signal": "NO_TRADE",
                "note": "provider_not_live",
                "market_type": "CRYPTO",
                "paper_only": True,
            }
        return eng.analyze_symbol(symbol).to_dict()

    def _fav_meta(self, symbol: str) -> tuple[bool, int]:
        if self.favorites is None:
            return False, 0
        fav = self.favorites.get(symbol, market_type="CRYPTO")
        if fav and fav.active:
            return True, int(fav.priority or 0)
        return False, 0

    def _row_from_quote(self, symbol: str) -> dict[str, Any]:
        """Quote-only card when signals are off or analysis unavailable."""
        is_fav, pri = self._fav_meta(symbol)
        if not is_live_crypto_provider(self.provider):
            return card_from_parts(
                symbol=normalize_crypto_app_symbol(symbol),
                price=None,
                change_pct=None,
                volume=None,
                signal="NO_DATA",
                model_score=None,
                entry=None,
                stop=None,
                target=None,
                risk_reward=None,
                trend=None,
                last_update=None,
                live_status="UNAVAILABLE",
                is_favorite=is_fav,
                favorite_priority=pri,
                note="provider_not_live",
            )
        try:
            q = self.provider.get_quote(symbol)
            stats = self.provider.ticker_stats(symbol)
            badge = live_status_badge(
                has_quote=True, data_source_kind=q.data_source_kind, ts=q.ts
            )
            return card_from_parts(
                symbol=q.symbol,
                price=q.price,
                change_pct=stats.get("change_pct"),
                volume=stats.get("volume", q.volume),
                signal="WAIT" if settings.crypto_signals_enabled else "NO_DATA",
                model_score=None,
                entry=None,
                stop=None,
                target=None,
                risk_reward=None,
                trend="—",
                last_update=q.ts,
                live_status=badge,
                is_favorite=is_fav,
                favorite_priority=pri,
                note="quote_only" if not settings.crypto_signals_enabled else "awaiting_signal",
                data_source_kind=q.data_source_kind,
                provider=q.provider,
            )
        except Exception as exc:  # noqa: BLE001
            return card_from_parts(
                symbol=normalize_crypto_app_symbol(symbol),
                price=None,
                change_pct=None,
                volume=None,
                signal="NO_DATA",
                model_score=None,
                entry=None,
                stop=None,
                target=None,
                risk_reward=None,
                trend=None,
                last_update=None,
                live_status="UNAVAILABLE",
                is_favorite=is_fav,
                favorite_priority=pri,
                note=str(exc),
            )

    def _row_from_signal(self, sig: dict[str, Any]) -> dict[str, Any]:
        symbol = normalize_crypto_app_symbol(str(sig.get("symbol") or ""))
        is_fav, pri = self._fav_meta(symbol)
        plan = sig.get("trade_plan") or {}
        mtf = sig.get("mtf") or {}
        trend = mtf.get("1h") or mtf.get("15m") or mtf.get("4h") or "—"
        change_pct = None
        volume = None
        price = None
        ts = None
        kind = sig.get("data_source_kind")
        provider = sig.get("provider")
        if is_live_crypto_provider(self.provider):
            try:
                q = self.provider.get_quote(symbol)
                price = q.price
                ts = q.ts
                kind = q.data_source_kind
                provider = q.provider
                stats = self.provider.ticker_stats(symbol) if hasattr(self.provider, "ticker_stats") else {}
                change_pct = stats.get("change_pct")
                volume = stats.get("volume", q.volume)
            except Exception:  # noqa: BLE001
                pass
        badge = live_status_badge(has_quote=price is not None, data_source_kind=kind, ts=ts)
        row = card_from_parts(
            symbol=symbol,
            price=price,
            change_pct=change_pct,
            volume=volume,
            signal=str(sig.get("signal") or "NO_TRADE"),
            model_score=sig.get("model_score"),
            entry=plan.get("entry"),
            stop=plan.get("stop_loss"),
            target=plan.get("target_1"),
            risk_reward=plan.get("risk_reward"),
            trend=str(trend),
            last_update=ts,
            live_status=badge,
            is_favorite=is_fav,
            favorite_priority=pri,
            note=str(sig.get("note") or ""),
            data_source_kind=kind,
            provider=provider,
        )
        row["trade_plan"] = plan
        row["risk"] = sig.get("risk")
        row["confirmations"] = sig.get("confirmations") or []
        row["mtf"] = mtf
        row["opportunity"] = sig.get("opportunity")
        row["model_score_definition"] = sig.get("model_score_definition")
        row["probability_label"] = sig.get("probability_label")
        return row

    def dashboard(self, limit: int = 40, *, emit_alerts: bool = True) -> dict[str, Any]:
        """Crypto UI dashboard — favorites-first sorted cards."""
        st = self.status()
        lim = max(1, min(100, int(limit)))
        rows: list[dict[str, Any]] = []

        if not settings.crypto_enabled:
            return {
                "market_type": MarketType.CRYPTO.value,
                "enabled": False,
                "rows": [],
                "sections": sectionize([]),
                "status": st,
                "paper_only": True,
                "live_trading": False,
                "count": 0,
                "note": "CRYPTO_ENABLED=false",
            }

        # Prefer favorite symbols first in scan universe
        fav_syms: list[str] = []
        if self.favorites is not None:
            fav_syms = [f.symbol for f in self.favorites.list_favorites(market_type="CRYPTO")]

        scan_syms: list[str] | None = None
        if is_live_crypto_provider(self.provider) and self.provider.has_market_data():
            universe = list(self.provider.list_symbols())
            # Favorites first, then rest (capped)
            ordered: list[str] = []
            seen: set[str] = set()
            for s in fav_syms + universe:
                s = normalize_crypto_app_symbol(s)
                if s and s not in seen:
                    seen.add(s)
                    ordered.append(s)
            scan_syms = ordered[: max(lim, len(fav_syms))]

        signals: list[dict[str, Any]] = []
        if settings.crypto_signals_enabled and scan_syms is not None:
            signals = self.scan(scan_syms)
            by_sym = {normalize_crypto_app_symbol(str(s.get("symbol") or "")): s for s in signals}
            for sym in scan_syms or []:
                if sym in by_sym:
                    rows.append(self._row_from_signal(by_sym[sym]))
                else:
                    rows.append(self._row_from_quote(sym))
        elif scan_syms is not None:
            for sym in (scan_syms or [])[:lim]:
                rows.append(self._row_from_quote(sym))

        rows = sort_dashboard_rows(rows)[:lim]
        sections = sectionize(rows)

        alerts_emitted = 0
        if emit_alerts and self._emit_signal_alerts and self.alerts is not None and signals:
            try:
                alerts_emitted = emit_crypto_signal_alerts(
                    self.alerts, rows, favorites=self.favorites
                )
            except Exception:  # noqa: BLE001
                alerts_emitted = 0

        return {
            "market_type": MarketType.CRYPTO.value,
            "enabled": True,
            "rows": rows,
            "sections": sections,
            "status": st,
            "paper_only": True,
            "live_trading": False,
            "tradeable": False,
            "count": len(rows),
            "alerts_emitted": alerts_emitted,
            "sort": "FAVORITES → STRONG_BUY → BUY → WAIT → SELL → STRONG_SELL",
            "principle": "CRYPTO UI · SIGNAL ≠ EXECUTION · FAVORITE ≠ BUY · PAPER ONLY",
            "note": st.get("ui", {}).get("message"),
        }

    def detail(self, symbol: str, timeframe: str = "15m") -> dict[str, Any]:
        """Coin detail: price, chart, indicators, signal, plan, accuracy, risk."""
        sym = normalize_crypto_app_symbol(symbol)
        sig = self.signal(sym) if settings.crypto_signals_enabled else {}
        row = self._row_from_signal(sig) if sig.get("symbol") else self._row_from_quote(sym)
        chart = self.chart(sym, timeframe=timeframe)

        indicators: dict[str, Any] = {}
        # Surface confirmations / mtf as indicator summary (full IndicatorSet lives in engine)
        indicators["confirmations"] = sig.get("confirmations") or row.get("confirmations") or []
        indicators["mtf"] = sig.get("mtf") or row.get("mtf") or {}
        indicators["model_score"] = sig.get("model_score") or row.get("model_score")
        indicators["model_score_definition"] = sig.get("model_score_definition")
        indicators["probability_label"] = sig.get("probability_label") or "NOT_A_PROBABILITY"

        accuracy: dict[str, Any] = {
            "historical_accuracy_pct": None,
            "label": "GEÇMİŞ DOĞRULUK",
            "note": "Model skoru ≠ kalibre olasılık ≠ geçmiş doğruluk",
            "sample_size": 0,
        }
        try:
            from prediction.store import PredictionStore

            store = PredictionStore()
            # Best-effort: filter by symbol if store supports listing
            if hasattr(store, "list_for_symbol"):
                hist = store.list_for_symbol(sym) or []
                accuracy["sample_size"] = len(hist)
            elif self.favorites is not None:
                perf = self.favorites.performance(market_type="CRYPTO")
                accuracy["historical_accuracy_pct"] = perf.get("win_rate")
                accuracy["sample_size"] = perf.get("signals") or 0
                accuracy["note"] = perf.get("note") or accuracy["note"]
        except Exception:  # noqa: BLE001
            pass

        return {
            "market_type": MarketType.CRYPTO.value,
            "symbol": sym,
            "display": to_display_symbol(sym),
            "price": row.get("price"),
            "change_pct": row.get("change_pct"),
            "volume": row.get("volume"),
            "live_status": row.get("live_status"),
            "last_update": row.get("last_update"),
            "last_update_ago": row.get("last_update_ago"),
            "signal": row.get("signal"),
            "decision_label": row.get("decision_label"),
            "confidence": row.get("confidence"),
            "model_score": row.get("model_score"),
            "indicators": indicators,
            "trade_plan": row.get("trade_plan") or sig.get("trade_plan"),
            "risk": row.get("risk") or sig.get("risk"),
            "prediction_accuracy": accuracy,
            "chart": chart,
            "timeframes": list(SUPPORTED_TF),
            "is_favorite": row.get("is_favorite"),
            "card": row,
            "paper_only": True,
            "live_trading": False,
            "note": "Detay görünümü — canlı emir / broker yok",
        }

    def chart(self, symbol: str, timeframe: str = "15m", lookback: int = 120) -> dict[str, Any]:
        sym = normalize_crypto_app_symbol(symbol)
        try:
            tf = normalize_timeframe(timeframe)
        except ValueError:
            tf = "15m"
        if not is_live_crypto_provider(self.provider):
            return bars_to_chart([], symbol=sym, timeframe=tf)
        try:
            bars = self.provider.get_bars_tf(sym, tf, lookback=lookback)
        except Exception:  # noqa: BLE001
            bars = self.provider.get_bars(sym, lookback=lookback) if tf == "15m" else []
        return bars_to_chart(bars, symbol=sym, timeframe=tf)

    def backfill(self, symbol: str, timeframe: str = "15m") -> dict[str, Any]:
        if not is_live_crypto_provider(self.provider):
            return {"ok": False, "note": "live crypto provider required", "symbol": symbol}
        return backfill_symbol(self.provider, symbol, timeframe=timeframe).to_dict()

    def markets_catalog(self) -> dict[str, Any]:
        return {
            "markets": [
                {
                    "id": MarketType.BIST.value,
                    "label": "BIST",
                    "enabled": True,
                    "default": True,
                    "path": "/api/daily",
                },
                {
                    "id": MarketType.CRYPTO.value,
                    "label": "CRYPTO",
                    "enabled": bool(settings.crypto_enabled),
                    "default": False,
                    "path": "/api/crypto/dashboard",
                    "ready": bool(settings.crypto_enabled and settings.paribu_enabled),
                    "signals": bool(settings.crypto_signals_enabled),
                },
            ],
            "active_default": MarketType.BIST.value,
            "nav": ["DASHBOARD", "BIST", "CRYPTO", "FAVORITES", "PORTFOLIO", "SETTINGS"],
        }
