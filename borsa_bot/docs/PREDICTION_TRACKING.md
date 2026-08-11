"""Prediction Accuracy & Forecast Tracking Engine (§104)

Independent measurement module. Does **not** decide trades, veto risk, or execute.

## Separation of concerns

| Engine | Role |
|--------|------|
| Trading / AI | KARAR VERİR — produces signals & forecasts |
| Prediction Tracking | ÖLÇER — records, evaluates, calibrates, rates |
| Risk | VETO EDER |
| Execution | EMRİ UYGULAR |

## Critical metric distinction

**METRIC 1 — TAHMİN OLASILIĞI (Current Forecast Probability)**  
Model’s stated probability for the *current* setup (e.g. “%80 rise”).

**METRIC 2 — GEÇMİŞ DOĞRULUK (Historical Forecast Accuracy)**  
Realized hit-rate of *past* predictions vs market prices.

These must never be shown as the same percentage.

## Flow

1. On scan: create immutable `PREDICTION_RECORD` + multi-horizon `MODEL_FORECAST` (1H/3H/1D/3D/1W; optional longer).
2. Each horizon: LOW / BASE / HIGH range, price + %, confidence, probability.
3. When horizon matures: fetch actual price → direction accuracy, return error (pp), MAE/MAPE/RMSE aggregates, target hit, quality score 0–100.
4. Trade-plan outcomes: STOP_HIT / TARGET_1|2|3_HIT / TIMEOUT (path-aware when high/low available).
5. Aggregate by symbol, strategy, model version, regime, sector.
6. Confidence calibration buckets + Brier score + calibration curve.
7. Self-rating grades S…F from objective history; sample tiers INSUFFICIENT / PROVISIONAL / VALIDATED / HIGH_CONFIDENCE (config).
8. Rolling last 20/50/100 → MODEL DEGRADATION alert when recent accuracy collapses.
9. Stock-specific reliability may apply a *display* confidence penalty — never changes Risk/Execution.

## No look-ahead / no fiction

- Forecast uses only data available at prediction timestamp T.
- Accuracy/ratings computed only from stored predictions + later market prices.
- Insufficient samples → grade `INSUFFICIENT`, never A+ on n&lt;50.
- Error categories prefer objective feature flags (false breakout, news block, regime change); no invented narratives.

## APIs

- `GET /api/predictions/{symbol}` — AI FORECAST + AI RELIABILITY + history/timeline
- `GET /api/predictions/report` — reliability + calibration buckets
- `GET /api/predictions/leaderboard` — strategy/model board + CURRENT CHAMPION (validated OOS-style only)
- `POST /api/predictions/evaluate` — force due-horizon evaluation

## Config

- `PREDICTION_MODEL_VERSION`
- `PRED_SAMPLE_INSUFFICIENT` (default 50)
- `PRED_SAMPLE_PROVISIONAL` (100)
- `PRED_SAMPLE_VALIDATED` (500)
- `PRED_DEGRADATION_DROP_PP`

## Storage

SQLite `database/predictions.db` — predictions are insert-only (immutable).

## UI labels

Always name:

- **Tahmin olasılığı** for current forecast probability
- **Geçmiş doğruluk** for historical accuracy
"""
