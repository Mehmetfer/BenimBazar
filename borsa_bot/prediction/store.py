from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT
from prediction.models import HorizonEvaluation, HorizonForecast, PredictionRecord


class PredictionStore:
    """Immutable prediction records + evaluations. Never rewrites predictions."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "predictions.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    prediction_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price_at_prediction REAL NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    probability REAL NOT NULL,
                    entry_price REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    target_3 REAL,
                    strategy TEXT,
                    market_regime TEXT,
                    sector TEXT,
                    time_horizon_primary TEXT,
                    model_version TEXT,
                    strategy_version TEXT,
                    features_snapshot TEXT,
                    forecasts_json TEXT NOT NULL,
                    is_favorite INTEGER DEFAULT 0,
                    market_data_source TEXT DEFAULT 'UNKNOWN',
                    prediction_source TEXT DEFAULT 'UNKNOWN',
                    data_source_kind TEXT DEFAULT 'UNKNOWN'
                );
                CREATE TABLE IF NOT EXISTS prediction_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    price_at_prediction REAL,
                    forecast_price REAL,
                    forecast_return_pct REAL,
                    actual_price REAL,
                    actual_return_pct REAL,
                    return_error_pp REAL,
                    direction_forecast TEXT,
                    direction_actual TEXT,
                    direction_correct INTEGER,
                    target_hit INTEGER,
                    abs_error_pct REAL,
                    confidence REAL,
                    probability REAL,
                    strategy TEXT,
                    market_regime TEXT,
                    sector TEXT,
                    model_version TEXT,
                    prediction_quality_score REAL,
                    error_category TEXT,
                    market_data_source TEXT DEFAULT 'UNKNOWN',
                    actual_result_source TEXT DEFAULT 'UNKNOWN',
                    data_source_kind TEXT DEFAULT 'UNKNOWN',
                    UNIQUE(prediction_id, horizon)
                );
                CREATE TABLE IF NOT EXISTS forecast_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    original_prediction_id TEXT NOT NULL,
                    revised_at TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    original_return_pct REAL,
                    current_return_pct REAL,
                    note TEXT
                );
                CREATE TABLE IF NOT EXISTS trade_plan_outcomes (
                    prediction_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    details TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pred_symbol_ts ON predictions(symbol, timestamp);
                CREATE INDEX IF NOT EXISTS idx_eval_symbol_h ON prediction_evaluations(symbol, horizon);
                """
            )
            from database.migrate_provenance import migrate_predictions_db

            migrate_predictions_db(c)

    def insert_prediction(self, rec: PredictionRecord) -> str:
        # Immutable insert — reject updates / source mutation
        from data.provenance import SourceMutationError, parse_data_source_kind

        with self._conn() as c:
            existing = c.execute(
                "SELECT prediction_id, market_data_source, data_source_kind FROM predictions WHERE prediction_id=?",
                (rec.prediction_id,),
            ).fetchone()
            if existing:
                # Refuse SIMULATED → LIVE style mutation via re-insert
                old_kind = parse_data_source_kind(
                    existing["data_source_kind"] or existing["market_data_source"]
                )
                new_kind = parse_data_source_kind(rec.data_source_kind or rec.market_data_source)
                if old_kind != new_kind:
                    raise SourceMutationError(
                        f"prediction source immutable: {old_kind.value} → {new_kind.value}"
                    )
                return rec.prediction_id
            mds = parse_data_source_kind(rec.market_data_source).value
            ps = parse_data_source_kind(rec.prediction_source or rec.market_data_source).value
            dsk = parse_data_source_kind(rec.data_source_kind or rec.market_data_source).value
            mtype = (getattr(rec, "market_type", None) or "BIST").upper()
            if mtype not in {"BIST", "CRYPTO"}:
                mtype = "BIST"
            c.execute(
                """
                INSERT INTO predictions(
                    prediction_id, timestamp, symbol, price_at_prediction, signal, confidence,
                    probability, entry_price, stop_loss, target_1, target_2, target_3, strategy,
                    market_regime, sector, time_horizon_primary, model_version, strategy_version,
                    features_snapshot, forecasts_json, is_favorite,
                    market_data_source, prediction_source, data_source_kind, market_type
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rec.prediction_id,
                    rec.timestamp,
                    rec.symbol,
                    rec.price_at_prediction,
                    rec.signal,
                    rec.confidence,
                    rec.probability,
                    rec.entry_price,
                    rec.stop_loss,
                    rec.target_1,
                    rec.target_2,
                    rec.target_3,
                    rec.strategy,
                    rec.market_regime,
                    rec.sector,
                    rec.time_horizon_primary,
                    rec.model_version,
                    rec.strategy_version,
                    json.dumps(rec.features_snapshot, default=str),
                    json.dumps([f.__dict__ if hasattr(f, "__dict__") else f for f in rec.forecasts]),
                    1 if rec.is_favorite else 0,
                    mds,
                    ps,
                    dsk,
                    mtype,
                ),
            )
        return rec.prediction_id

    def get_prediction(self, prediction_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM predictions WHERE prediction_id=?", (prediction_id,)).fetchone()
        if not row:
            return None
        return self._pred_row(row)

    def recent_predictions(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM predictions"
        args: list[Any] = []
        if symbol:
            q += " WHERE symbol=?"
            args.append(symbol.upper())
        q += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [self._pred_row(r) for r in rows]

    def pending_evaluations(self, now_iso: str | None = None) -> list[tuple[dict, dict]]:
        """Return (prediction, forecast_horizon_dict) due for evaluation and not yet evaluated."""
        from datetime import datetime, timezone
        from prediction.models import HORIZON_SECONDS, TimeHorizon

        now = datetime.now(timezone.utc)
        out: list[tuple[dict, dict]] = []
        with self._conn() as c:
            preds = c.execute("SELECT * FROM predictions ORDER BY timestamp ASC").fetchall()
            done = {
                (r["prediction_id"], r["horizon"])
                for r in c.execute("SELECT prediction_id, horizon FROM prediction_evaluations").fetchall()
            }
        for prow in preds:
            pred = self._pred_row(prow)
            try:
                ts = datetime.fromisoformat(pred["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                continue
            for fc in pred.get("forecasts") or []:
                h = fc.get("horizon")
                if (pred["prediction_id"], h) in done:
                    continue
                try:
                    th = TimeHorizon(h)
                except ValueError:
                    continue
                due = ts.timestamp() + HORIZON_SECONDS[th]
                if now.timestamp() >= due:
                    out.append((pred, fc))
        return out

    def insert_evaluation(self, ev: HorizonEvaluation) -> None:
        from data.provenance import parse_data_source_kind

        mds = parse_data_source_kind(ev.market_data_source).value
        ars = parse_data_source_kind(ev.actual_result_source).value
        dsk = parse_data_source_kind(ev.data_source_kind or ev.market_data_source).value
        with self._conn() as c:
            c.execute(
                """
                INSERT OR IGNORE INTO prediction_evaluations(
                    prediction_id, symbol, horizon, evaluated_at, price_at_prediction,
                    forecast_price, forecast_return_pct, actual_price, actual_return_pct,
                    return_error_pp, direction_forecast, direction_actual, direction_correct,
                    target_hit, abs_error_pct, confidence, probability, strategy, market_regime,
                    sector, model_version, prediction_quality_score, error_category,
                    market_data_source, actual_result_source, data_source_kind
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ev.prediction_id,
                    ev.symbol,
                    ev.horizon,
                    ev.evaluated_at,
                    ev.price_at_prediction,
                    ev.forecast_price,
                    ev.forecast_return_pct,
                    ev.actual_price,
                    ev.actual_return_pct,
                    ev.return_error_pp,
                    ev.direction_forecast,
                    ev.direction_actual,
                    1 if ev.direction_correct else 0,
                    None if ev.target_hit is None else (1 if ev.target_hit else 0),
                    ev.abs_error_pct,
                    ev.confidence,
                    ev.probability,
                    ev.strategy,
                    ev.market_regime,
                    ev.sector,
                    ev.model_version,
                    ev.prediction_quality_score,
                    ev.error_category,
                    mds,
                    ars,
                    dsk,
                ),
            )

    def update_prediction_source(self, prediction_id: str, new_kind: str) -> None:
        """Blocked in trading path — source is immutable."""
        from data.provenance import SourceMutationError

        raise SourceMutationError(
            f"Cannot update prediction {prediction_id} data_source_kind to {new_kind}"
        )

    def list_evaluations(
        self,
        *,
        symbol: str | None = None,
        horizon: str | None = None,
        strategy: str | None = None,
        regime: str | None = None,
        sector: str | None = None,
        model_version: str | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        clauses = []
        args: list[Any] = []
        if symbol:
            clauses.append("symbol=?")
            args.append(symbol.upper())
        if horizon:
            clauses.append("horizon=?")
            args.append(horizon)
        if strategy:
            clauses.append("strategy=?")
            args.append(strategy)
        if regime:
            clauses.append("market_regime=?")
            args.append(regime)
        if sector:
            clauses.append("sector=?")
            args.append(sector)
        if model_version:
            clauses.append("model_version=?")
            args.append(model_version)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        q = f"SELECT * FROM prediction_evaluations{where} ORDER BY evaluated_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def record_revision(
        self,
        symbol: str,
        original_prediction_id: str,
        horizon: str,
        original_return_pct: float,
        current_return_pct: float,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO forecast_revisions(symbol, original_prediction_id, revised_at, horizon,
                    original_return_pct, current_return_pct, note)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    symbol.upper(),
                    original_prediction_id,
                    utc_now().isoformat(),
                    horizon,
                    original_return_pct,
                    current_return_pct,
                    "FORECAST_REVISION",
                ),
            )

    def set_trade_plan_outcome(self, prediction_id: str, symbol: str, outcome: str, details: dict | None = None) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO trade_plan_outcomes(prediction_id, symbol, outcome, evaluated_at, details)
                VALUES (?,?,?,?,?)
                """,
                (prediction_id, symbol.upper(), outcome, utc_now().isoformat(), json.dumps(details or {})),
            )

    def latest_for_symbol(self, symbol: str) -> dict | None:
        rows = self.recent_predictions(symbol, limit=1)
        return rows[0] if rows else None

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def _pred_row(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["features_snapshot"] = json.loads(d.get("features_snapshot") or "{}")
        except json.JSONDecodeError:
            d["features_snapshot"] = {}
        try:
            d["forecasts"] = json.loads(d.get("forecasts_json") or "[]")
        except json.JSONDecodeError:
            d["forecasts"] = []
        d.pop("forecasts_json", None)
        d["is_favorite"] = bool(d.get("is_favorite"))
        return d
