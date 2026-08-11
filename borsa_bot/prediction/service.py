"""Prediction Tracking Service — MEASURES only; never decides trades.

METRIC 1 = current forecast probability (model's stated odds for this setup)
METRIC 2 = historical forecast accuracy (realized outcomes vs past predictions)
These must never be conflated in UI or APIs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from alerts.events import AlertEventType, AlertPriority, TradingAlertEvent
from alerts.manager import AlertManager
from config.models import (
    IndicatorSet,
    MarketRegime,
    OpportunityMetrics,
    AITradePlan,
    utc_now,
)
from config.settings import Settings, settings as default_settings
from prediction.evaluate import evaluate_horizon, resolve_trade_plan_outcome
from prediction.forecast import MODEL_VERSION, STRATEGY_VERSION, generate_horizon_forecasts
from prediction.models import (
    DEFAULT_ACTIVE_HORIZONS,
    HORIZON_SECONDS,
    HorizonForecast,
    PredictionRecord,
    ReliabilityGrade,
    ReliabilityReport,
    SampleTier,
    TimeHorizon,
    TradePlanOutcome,
)
from prediction.rating import (
    build_reliability_report,
    calibration_buckets,
    leaderboard,
    pick_champion,
)
from prediction.store import PredictionStore


class PredictionTrackingService:
    """Independent measurement layer.

    TradingEngine decides · RiskEngine vetoes · ExecutionEngine executes ·
    PredictionTracking measures. Never mix these.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        store: PredictionStore | None = None,
        alert_manager: AlertManager | None = None,
    ) -> None:
        self.settings = settings or default_settings
        self.store = store or PredictionStore()
        self.alert_manager = alert_manager
        self.model_version = str(getattr(self.settings, "prediction_model_version", MODEL_VERSION))
        self.strategy_version = STRATEGY_VERSION
        self._last_degradation_alert: datetime | None = None
        self._latest_by_symbol: dict[str, PredictionRecord] = {}

    def record_prediction(
        self,
        *,
        symbol: str,
        price: float,
        signal: str,
        confidence: float,
        probability: float,
        ind: IndicatorSet,
        regime: MarketRegime,
        sector: str = "",
        strategy: str = "ensemble",
        opp: OpportunityMetrics | None = None,
        plan: AITradePlan | None = None,
        is_favorite: bool = False,
        features_snapshot: dict[str, Any] | None = None,
        primary_horizon: str = "1D",
        market_data_source: str | None = None,
    ) -> PredictionRecord | None:
        """Create immutable PREDICTION_RECORD. No look-ahead: only T-available inputs."""
        from data.provenance import is_never_tradeable, parse_data_source_kind, tradeable_flag

        # Skip pure noise; still record WAIT/NO_TRADE when confidence meaningful
        sig = (signal or "").upper()
        if sig in {"HOLD"} and confidence < 40:
            return None

        # Provenance from indicator/bars — never trust caller LIVE without provider seal
        ind_src = parse_data_source_kind(getattr(ind, "data_source_kind", None))
        mds = parse_data_source_kind(market_data_source or ind_src)
        # Caller cannot elevate to LIVE via argument if indicator is simulated
        if is_never_tradeable(ind_src) and not is_never_tradeable(mds):
            mds = ind_src

        # Throttle identical re-scans (dashboard poll) — still immutable when we do write
        prev = self.store.latest_for_symbol(symbol)
        if prev:
            try:
                ts = datetime.fromisoformat(str(prev["timestamp"]).replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - ts).total_seconds()
            except Exception:  # noqa: BLE001
                age = 99999
            same_sig = str(prev.get("signal") or "").upper() == sig
            close_conf = abs(float(prev.get("confidence") or 0) - float(confidence)) < 2.0
            if age < 900 and same_sig and close_conf:
                # Return existing as card source without mutating
                return None

        forecasts = generate_horizon_forecasts(
            price=price,
            ind=ind,
            signal=sig,
            confidence=float(confidence),
            opp=opp,
            plan=plan,
            regime=regime,
            horizons=DEFAULT_ACTIVE_HORIZONS,
        )
        entry = plan.entry_price if plan else price
        stop = plan.stop_loss if plan else None
        t1 = plan.target1.price if plan else None
        t2 = plan.target2.price if plan else None
        t3 = plan.target3.price if plan else None

        # Capture previous forecast for revision tracking (original stays immutable)
        if prev and forecasts:
            old_map = {f.get("horizon"): f for f in (prev.get("forecasts") or [])}
            for fc in forecasts:
                old = old_map.get(fc.horizon)
                if old and abs(float(old.get("base_return_pct") or 0) - fc.base_return_pct) >= 0.5:
                    self.store.record_revision(
                        symbol,
                        prev["prediction_id"],
                        fc.horizon,
                        float(old.get("base_return_pct") or 0),
                        fc.base_return_pct,
                    )

        rec = PredictionRecord(
            prediction_id=PredictionStore.new_id(),
            timestamp=utc_now().isoformat(),
            symbol=symbol.upper(),
            price_at_prediction=round(price, 4),
            signal=sig,
            confidence=round(float(confidence), 2),
            probability=round(float(probability), 4),
            entry_price=round(entry, 4) if entry is not None else None,
            stop_loss=round(stop, 4) if stop is not None else None,
            target_1=round(t1, 4) if t1 is not None else None,
            target_2=round(t2, 4) if t2 is not None else None,
            target_3=round(t3, 4) if t3 is not None else None,
            strategy=strategy,
            market_regime=regime.value if hasattr(regime, "value") else str(regime),
            sector=sector or "",
            time_horizon_primary=primary_horizon,
            model_version=self.model_version,
            strategy_version=self.strategy_version,
            features_snapshot={
                **dict(features_snapshot or {}),
                "tradeable": tradeable_flag(mds, verified=False),
            },
            forecasts=forecasts,
            is_favorite=is_favorite,
            market_data_source=mds.value,
            prediction_source=mds.value,
            data_source_kind=mds.value,
        )
        self.store.insert_prediction(rec)
        self._latest_by_symbol[rec.symbol] = rec
        return rec

    def evaluate_due(
        self,
        price_lookup: Callable[[str], float | None],
        *,
        actual_result_source: str | None = None,
    ) -> int:
        """Evaluate matured horizons against actual market prices."""
        from data.provenance import parse_data_source_kind

        pending = self.store.pending_evaluations()
        # Group for trade-plan outcomes
        by_pred: dict[str, list[tuple[dict, dict]]] = {}
        count = 0
        for pred, fc in pending:
            by_pred.setdefault(pred["prediction_id"], []).append((pred, fc))

        for pid, items in by_pred.items():
            pred = items[0][0]
            actual = price_lookup(pred["symbol"])
            if actual is None or actual <= 0:
                continue
            pred_src = parse_data_source_kind(pred.get("market_data_source") or pred.get("data_source_kind"))
            # Actual source: explicit from caller (provider), else inherit prediction source
            # Never silently promote to LIVE
            ars = parse_data_source_kind(actual_result_source or pred_src)
            for pred, fc in items:
                target_ret = None
                if pred.get("target_1") and pred.get("price_at_prediction"):
                    px0 = float(pred["price_at_prediction"])
                    if px0 > 0:
                        target_ret = (float(pred["target_1"]) / px0 - 1.0) * 100.0
                ev = evaluate_horizon(
                    prediction_id=pred["prediction_id"],
                    symbol=pred["symbol"],
                    horizon=fc["horizon"],
                    price_at_prediction=float(pred["price_at_prediction"]),
                    forecast_price=float(fc.get("forecast_price") or 0),
                    forecast_return_pct=float(fc.get("forecast_return_pct") or fc.get("base_return_pct") or 0),
                    direction_forecast=str(fc.get("direction") or "FLAT"),
                    actual_price=float(actual),
                    confidence=float(fc.get("confidence") or pred.get("confidence") or 50),
                    probability=float(fc.get("probability") or pred.get("probability") or 0.5),
                    strategy=str(pred.get("strategy") or ""),
                    market_regime=str(pred.get("market_regime") or ""),
                    sector=str(pred.get("sector") or ""),
                    model_version=str(pred.get("model_version") or ""),
                    features=pred.get("features_snapshot") if isinstance(pred.get("features_snapshot"), dict) else {},
                    target_return_pct=target_ret,
                    market_data_source=pred_src.value,
                    actual_result_source=ars.value,
                )
                self.store.insert_evaluation(ev)
                count += 1

            horizons_done = {fc["horizon"] for _, fc in items}
            if "1D" in horizons_done or "1W" in horizons_done:
                # Path approx: use current price as both high/low when no path store
                timed_out = "1W" in horizons_done
                outcome = resolve_trade_plan_outcome(
                    price_at=float(pred["price_at_prediction"]),
                    stop=pred.get("stop_loss"),
                    t1=pred.get("target_1"),
                    t2=pred.get("target_2"),
                    t3=pred.get("target_3"),
                    path_high=float(actual),
                    path_low=float(actual),
                    timed_out=timed_out,
                )
                if outcome != TradePlanOutcome.OPEN or timed_out:
                    self.store.set_trade_plan_outcome(pid, pred["symbol"], outcome.value)

        self._maybe_alert_degradation()
        return count

    def _maybe_alert_degradation(self) -> None:
        if self.alert_manager is None:
            return
        now = datetime.now(timezone.utc)
        if self._last_degradation_alert and (now - self._last_degradation_alert).total_seconds() < 3600:
            return
        report = self.reliability_report()
        if not report.degradation:
            return
        self._last_degradation_alert = now
        try:
            self.alert_manager.publish(
                TradingAlertEvent(
                    event_type=AlertEventType.RISK_ALERT,
                    symbol=None,
                    priority=AlertPriority.HIGH,
                    title="AI TAHMİN DOĞRULUĞU DÜŞÜYOR",
                    message=(
                        f"MODEL DEGRADATION — Historical %{report.historical_accuracy_pct or 0} → "
                        f"Last100 %{report.last_100 or 0} → "
                        f"Last50 %{report.last_50 or 0} → "
                        f"Last20 %{report.last_20 or 0}"
                    ),
                    tts_text="Yapay zeka tahmin doğruluğu düşüyor. Model degradasyon uyarısı.",
                    payload={
                        "kind": "MODEL_DEGRADATION",
                        "historical_accuracy_pct": report.historical_accuracy_pct,
                        "last_100": report.last_100,
                        "last_50": report.last_50,
                        "last_20": report.last_20,
                        "note": "Geçmiş doğruluk ≠ tahmin olasılığı",
                    },
                    dedupe_key="MODEL_DEGRADATION",
                )
            )
        except Exception:  # noqa: BLE001
            pass

    def reliability_report(
        self,
        *,
        symbol: str | None = None,
        strategy: str | None = None,
        horizon: str | None = None,
        model_version: str | None = None,
        regime: str | None = None,
        sector: str | None = None,
        scope: str = "overall",
        key: str = "OVERALL",
        accuracy_bucket: str | None = None,
    ) -> ReliabilityReport:
        from data.provenance import filter_rows_by_accuracy_bucket, live_accuracy_display

        rows = self.store.list_evaluations(
            symbol=symbol,
            strategy=strategy,
            horizon=horizon,
            model_version=model_version,
            regime=regime,
            sector=sector,
        )
        if accuracy_bucket:
            rows = filter_rows_by_accuracy_bucket(rows, accuracy_bucket)
        parts = [p for p in [symbol, strategy, horizon, model_version, regime, sector, accuracy_bucket] if p]
        rep = build_reliability_report(
            rows,
            scope=scope if not parts else "/".join(parts),
            key=key if not parts else "/".join(parts),
            cfg=self.settings,
        )
        if accuracy_bucket and accuracy_bucket.upper() == "LIVE":
            live = live_accuracy_display(rows if accuracy_bucket else self.store.list_evaluations())
            if live["status"] == "INSUFFICIENT DATA":
                rep.historical_accuracy_pct = None
                rep.directional_accuracy = None
                rep.sample_tier = SampleTier.INSUFFICIENT.value
                rep.grade = ReliabilityGrade.INSUFFICIENT.value
                rep.note = "LIVE ACCURACY: INSUFFICIENT DATA — henüz ölçülecek LIVE veri yok (0% değildir)."
        return rep

    def accuracy_by_source(self, *, symbol: str | None = None) -> dict[str, Any]:
        """LIVE / SIMULATED / TEST / BACKTEST accuracy kept separate."""
        from data.provenance import filter_rows_by_accuracy_bucket, live_accuracy_display

        rows = self.store.list_evaluations(symbol=symbol)
        out: dict[str, Any] = {
            "LIVE": live_accuracy_display(rows),
            "SIMULATED": None,
            "TEST": None,
            "BACKTEST": None,
        }
        for bucket in ("SIMULATED", "TEST", "BACKTEST"):
            subset = filter_rows_by_accuracy_bucket(rows, bucket)
            if not subset:
                out[bucket] = {
                    "bucket": bucket,
                    "status": "INSUFFICIENT DATA",
                    "historical_accuracy_pct": None,
                    "sample_size": 0,
                }
            else:
                hits = sum(1 for r in subset if r.get("direction_correct"))
                n = len(subset)
                out[bucket] = {
                    "bucket": bucket,
                    "status": "OK",
                    "historical_accuracy_pct": round(hits / n * 100, 1),
                    "sample_size": n,
                }
        return out

    def symbol_card(self, symbol: str, latest: PredictionRecord | dict | None = None) -> dict[str, Any]:
        """AI FORECAST + AI RELIABILITY payload with explicit metric labels."""
        sym = symbol.upper()
        pred_dict: dict | None
        if isinstance(latest, PredictionRecord):
            pred_dict = latest.to_dict()
        elif isinstance(latest, dict):
            pred_dict = latest
        else:
            pred_dict = self.store.latest_for_symbol(sym)

        forecast_rows = []
        bias = "NEUTRAL"
        if pred_dict:
            for fc in pred_dict.get("forecasts") or []:
                base = float(fc.get("base_return_pct") or fc.get("forecast_return_pct") or 0)
                direction = fc.get("direction") or ("UP" if base > 0.15 else ("DOWN" if base < -0.15 else "FLAT"))
                arrow = "↑" if direction == "UP" else ("↓" if direction == "DOWN" else "→")
                forecast_rows.append(
                    {
                        "horizon": fc.get("horizon"),
                        "direction": direction,
                        "arrow": arrow,
                        "pct_base": fc.get("base_return_pct", fc.get("forecast_return_pct")),
                        "pct_low": fc.get("low_return_pct"),
                        "pct_high": fc.get("high_return_pct"),
                        "price_base": fc.get("forecast_price"),
                        # METRIC 1 — named explicitly
                        "tahmin_olasiligi": round(float(fc.get("probability") or 0) * 100),
                        "confidence": fc.get("confidence"),
                        "uncertainty": fc.get("uncertainty"),
                        "kind": "MODEL_FORECAST",
                        "forecast_probability_label": "TAHMİN OLASILIĞI",
                    }
                )
            ups = sum(1 for r in forecast_rows if (r.get("pct_base") or 0) > 0.15)
            downs = sum(1 for r in forecast_rows if (r.get("pct_base") or 0) < -0.15)
            if downs > ups and downs >= 2:
                bias = "BEARISH FORECAST"
            elif ups > downs and ups >= 2:
                bias = "BULLISH FORECAST"

        overall = self.reliability_report(symbol=sym, scope="symbol", key=sym)
        by_hz: dict[str, Any] = {}
        for hz in ("1H", "3H", "1D", "3D", "1W"):
            r = self.reliability_report(symbol=sym, horizon=hz, scope="horizon", key=f"{sym}/{hz}")
            by_hz[hz] = {
                "grade": r.grade,
                "gecmis_dogruluk": r.historical_accuracy_pct,
                "sample_size": r.sample_size,
                "sample_tier": r.sample_tier,
            }

        # Stock-specific confidence penalty (display/advisory only — does NOT change trade decision)
        penalty = 0.0
        if overall.grade in {"D", "F"} and overall.sample_tier in {"VALIDATED", "HIGH_CONFIDENCE"}:
            penalty = 0.15
        elif overall.grade == "C" and overall.sample_tier != "INSUFFICIENT_DATA":
            penalty = 0.08

        cal = calibration_buckets(
            self.store.list_evaluations(symbol=sym, limit=2000)
        )

        return {
            "symbol": sym,
            "has_forecast": pred_dict is not None,
            "prediction_id": pred_dict.get("prediction_id") if pred_dict else None,
            "forecast_bias": bias,
            "signal": pred_dict.get("signal") if pred_dict else None,
            "timestamp": pred_dict.get("timestamp") if pred_dict else None,
            "market_data_source": (pred_dict or {}).get("market_data_source") or "UNKNOWN",
            "prediction_source": (pred_dict or {}).get("prediction_source") or "UNKNOWN",
            "data_source_kind": (pred_dict or {}).get("data_source_kind") or "UNKNOWN",
            "tradeable": False
            if not pred_dict
            else (
                str(pred_dict.get("data_source_kind") or pred_dict.get("market_data_source") or "")
                in {"LIVE", "DELAYED", "BROKER"}
            ),
            "ai_forecast": forecast_rows,
            "current_forecast_probability": round(float(pred_dict.get("probability") or 0) * 100)
            if pred_dict
            else None,
            "current_forecast_probability_label": "TAHMİN OLASILIĞI",
            "ai_reliability": {
                "overall_grade": overall.grade,
                "gecmis_dogruluk": overall.historical_accuracy_pct,
                "historical_accuracy_label": "GEÇMİŞ DOĞRULUK",
                "last_20": overall.last_20,
                "last_50": overall.last_50,
                "last_100": overall.last_100,
                "sample_size": overall.sample_size,
                "sample_tier": overall.sample_tier,
                "brier_score": overall.brier_score,
                "calibration_note": overall.calibration_note,
                "calibration_buckets": cal,
                "by_horizon": by_hz,
                "confidence_penalty": penalty,
                "degradation_alert": overall.degradation,
                "mae": overall.mae,
                "note": overall.note,
                "by_source": self.accuracy_by_source(symbol=sym),
            },
            "decomposition": {
                "expected_return_pct": (pred_dict or {}).get("features_snapshot", {}).get("expected_return_pct")
                if pred_dict
                else None,
                "probability": round(float((pred_dict or {}).get("probability") or 0) * 100),
                "confidence": (pred_dict or {}).get("confidence"),
                "uncertainty": forecast_rows[2]["uncertainty"] if len(forecast_rows) > 2 else (
                    forecast_rows[0]["uncertainty"] if forecast_rows else None
                ),
            },
            "principle": (
                "TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK. "
                "SIMULATED accuracy ≠ LIVE accuracy. "
                "Prediction tracking MEASURES only — does not decide trades."
            ),
        }

    def history(self, symbol: str, limit: int = 40) -> list[dict[str, Any]]:
        preds = self.store.recent_predictions(symbol, limit=limit)
        out: list[dict[str, Any]] = []
        for pred in preds:
            evals = {
                e["horizon"]: e
                for e in self.store.list_evaluations(symbol=symbol, limit=500)
                if e["prediction_id"] == pred["prediction_id"]
            }
            for fc in pred.get("forecasts") or []:
                ev = evals.get(fc.get("horizon"))
                out.append(
                    {
                        "timestamp": pred["timestamp"],
                        "prediction_id": pred["prediction_id"],
                        "signal": pred["signal"],
                        "horizon": fc.get("horizon"),
                        "tahmin_pct": fc.get("base_return_pct", fc.get("forecast_return_pct")),
                        "gerceklesen_pct": ev.get("actual_return_pct") if ev else None,
                        "direction_correct": bool(ev["direction_correct"]) if ev else None,
                        "confidence": fc.get("confidence"),
                        "tahmin_olasiligi": round(float(fc.get("probability") or 0) * 100),
                        "quality_score": ev.get("prediction_quality_score") if ev else None,
                        "error_category": ev.get("error_category") if ev else None,
                        "evaluated": ev is not None,
                    }
                )
        return out

    def timeline(self, symbol: str, limit: int = 40) -> list[dict[str, Any]]:
        preds = list(reversed(self.store.recent_predictions(symbol, limit=limit)))
        return [
            {
                "timestamp": p["timestamp"],
                "signal": p["signal"],
                "confidence": p["confidence"],
                "probability": round(float(p.get("probability") or 0) * 100),
                "prediction_id": p["prediction_id"],
                "primary_forecast_pct": next(
                    (
                        f.get("base_return_pct")
                        for f in (p.get("forecasts") or [])
                        if f.get("horizon") == p.get("time_horizon_primary", "1D")
                    ),
                    (p.get("forecasts") or [{}])[0].get("base_return_pct") if p.get("forecasts") else None,
                ),
            }
            for p in preds
        ]

    def leaderboard(self, group_key: str = "strategy") -> list[dict[str, Any]]:
        return leaderboard(self.store.list_evaluations(), group_key=group_key)

    def champion(self, group_key: str = "model_version") -> dict[str, Any] | None:
        return pick_champion(self.leaderboard(group_key=group_key))

    def format_favorite_forecast_message(self, symbol: str, decision: str, card: dict[str, Any]) -> str:
        lines = [f"★ {symbol} {decision}", "", "AI FORECAST"]
        for row in card.get("ai_forecast") or []:
            pct = float(row.get("pct_base") or 0)
            sign = "+" if pct >= 0 else ""
            lines.append(
                f"{row.get('horizon')}: {sign}{pct:.1f}% "
                f"(Tahmin olasılığı %{row.get('tahmin_olasiligi', 0)})"
            )
        rel = card.get("ai_reliability") or {}
        lines.append("")
        lines.append(f"AI güvenilirlik derecesi: {rel.get('overall_grade', '—')}")
        gd = rel.get("gecmis_dogruluk")
        if gd is not None:
            lines.append(f"Geçmiş doğruluk: %{gd}")
        lines.append("Favori ≠ otomatik AL. Tahmin olasılığı ≠ geçmiş doğruluk.")
        return "\n".join(lines)

    def confidence_display_with_penalty(self, symbol: str, raw_confidence: float) -> float:
        """Advisory display penalty for weak stock-specific history. Does NOT alter decisions."""
        card = self.symbol_card(symbol)
        penalty = float((card.get("ai_reliability") or {}).get("confidence_penalty") or 0)
        return max(0.0, min(100.0, float(raw_confidence) * (1.0 - penalty)))
