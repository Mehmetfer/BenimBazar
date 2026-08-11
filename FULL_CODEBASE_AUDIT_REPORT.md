# TRADING BOT — FULL CODEBASE AUDIT REPORT

**Date:** 2026-08-11  
**Scope:** `/workspace` with primary focus on `borsa_bot/` (also `companion/`, `borsa_app/`)  
**Rule followed:** NO code changes, no refactors, no dependency changes, no behavior changes.  
**Method:** Static analysis of source, configs, schemas, tests, and API surface.

---

## 0. Executive snapshot

| Claim | Reality |
|--------|---------|
| ~17,100 LOC project | **ESTIMATE context:** `borsa_bot` `.py`+`.html` ≈ **13,569**; + companion source ≈ **877**; + Flutter `lib` ≈ **798**; + docs/reports varies. Core trading system ≈ **13.5k–15k** source lines. |
| Live trading bot | **Paper / simulated.** LIVE hard-blocked. |
| AI engine | **Heuristic rule engine**, not trained ML / LLM. |
| Live market data | **MOCK / SIMULATED** (default). Real adapter = stub / REQUIRED. |
| LIVE READY | **false** |

**OVERALL ARCHITECTURE:** NEEDS WORK  
**OVERALL SCORE:** **58 / 100**

---

## 1. PROJECT STRUCTURE

### Top-level layout

```
/workspace/
├── borsa_bot/          ★ Primary Python trading system (this audit focus)
├── companion/          Separate FastAPI paper app (simpler, weaker safety)
├── borsa_app/          Flutter client (separate UI path)
├── Application/, Core/, Services/   C# / persona artifacts (not trading core)
├── scripts/, test_page/
├── *.md, *_report.txt  Historical audits / education docs
└── .cursor/, .git/
```

### Counts (measured)

| Category | Count / Lines | Notes |
|----------|---------------|-------|
| `borsa_bot/**/*.py` | **113 files / 13,176 lines** | Includes tests |
| `borsa_bot` backend py (excl. tests) | **≈11,860 lines** | ESTIMATE from inventory |
| `borsa_bot/tests` | **1,316 lines** | 6 test modules + init |
| Frontend (`dashboard/static/index.html`) | **393 lines** | Single SPA |
| `borsa_bot/docs/*.md` | **222 lines** | 5 docs |
| Config (`config/*.py` + `.env.example` + requirements) | **≈592 lines** | |
| Companion source | **877 lines** | |
| Flutter `borsa_app/lib` | **≈798 lines / 4 dart files** | Separate product |
| Source files under borsa_bot+companion (py/html/js/css/md) | **133 files** | |

### Major `borsa_bot` packages (role)

| Path | Lines (approx) | Role | Status |
|------|----------------|------|--------|
| `strategy/service.py` | 1180 | God orchestrator: scan→decide→execute | IMPLEMENTED / God class |
| `trade_plan/engine.py` | 579 | Full AITradePlan | IMPLEMENTED |
| `prediction/service.py` | 474 | Forecast tracking orchestration | IMPLEMENTED |
| `dashboard/app.py` | 452 | FastAPI routes | IMPLEMENTED |
| `favorites/store.py` | 411 | Favorites SQLite | IMPLEMENTED |
| `dashboard/daily.py` | 388 | Daily home ranking/integrity | IMPLEMENTED |
| `indicators/engine.py` | 378 | TA indicators | IMPLEMENTED |
| `prediction/store.py` | 331 | Predictions DB | IMPLEMENTED |
| `signals/engine.py` | 329 | Scores + legacy plan | PARTIAL / DUPLICATED |
| `portfolio/ledger.py` | 283 | Paper portfolio SQLite | IMPLEMENTED |
| `data/providers.py` | 284 | Market data providers | PARTIAL |
| `risk/engine.py` | 213 | Pre-trade risk | PARTIAL |
| `profit/ev.py` | 177 | EV / decide_matrix | IMPLEMENTED |
| `execution/paper.py` | 60 | Paper broker only | PARTIAL |
| `news/analyzer.py` | 70 | Stub news | PARTIAL |
| `fundamental/provider.py` | 63 | Synthetic fundamentals | PARTIAL |
| `backtest/runner.py` | 160 | Synthetic backtest | PARTIAL |
| `walk_forward/runner.py` | 67 | Illustrative WF | PARTIAL |

---

## 2. ARCHITECTURE MAP (ACTUAL)

The idealized pipeline is **close but not exact**. Real flow:

```
SimulatedProvider.tick() / get_quote / get_bars
        ↓
TradingService.scan()                    ← single god orchestrator
        ↓
indicators.compute_indicators
technical.mtf / price_action / sector
factors.compute_factors
market_regime.detect_regime
universe.select_universe
news.score_news (often unavailable)
fundamental.score_fundamentals (synthetic if simulated)
alpha.run_alpha_ensemble + strategy.modules votes
ai.quality.assess_signal_quality  → ai_confidence (0–100 heuristic)
signals.build_trade_plan (legacy ATR plan)
profit.ev.compute_opportunity + estimate_p_win
profit.ev.decide_matrix           → STRONG_BUY / BUY / WAIT / …
risk.RiskEngine.evaluate_entry    → APPROVE / REDUCE / WAIT / REJECT
trade_plan.build_ai_trade_plan    → entry/stop/T1–T3/size (may demote)
prediction.record_prediction      → MEASURES only
favorites deeper + alerts
        ↓
_serialize → dashboard /api/daily UI
        ↓
[separate path] POST /api/execute
        ↓
SafetyGate + RiskEngine again
        ↓
PaperBroker.submit → PortfolioLedger
        ↓
alerts.emit_order_lifecycle
```

**Parallel / duplicated paths (not the same as main scan):**

- `engines/orchestrator.py` → long_term / swing / day_trading + `ai/ensemble.py` (multi-horizon API only)
- `companion/` → independent sim market + portfolio, weaker gates
- `borsa_app/` → Flutter UI (separate)

**Normalization layer:** No dedicated “DATA NORMALIZATION” module; quotes/bars used as-is from provider.

---

## 3. MODULE INVENTORY

### MARKET DATA

| Item | Status | Evidence |
|------|--------|----------|
| live price | MISSING (real) / IMPLEMENTED (sim) | `SimulatedProvider`; `HttpLiveProviderStub` never connects |
| OHLCV | IMPLEMENTED | `get_bars` |
| volume | IMPLEMENTED | bars/quotes |
| websocket | MISSING | polling only |
| polling | IMPLEMENTED | UI 15s; `tick()` on scan |
| market status | PARTIAL | BIST session approx in `data/integrity.py` |
| data freshness | IMPLEMENTED | `source_meta`, STALE / FRESH_SIMULATED |

**Overall:** PARTIAL

### TECHNICAL ANALYSIS

| Indicator | Status |
|-----------|--------|
| RSI, MACD, EMA, SMA, ATR, BB, ADX, Stoch, StochRSI, VWAP, MFI, CMF, CCI, Williams %R, OBV, momentum, ROC | IMPLEMENTED (`indicators/engine.py`) |
| support/resistance/pivot/structure | IMPLEMENTED |
| volume analysis | PARTIAL (relative vol + price_action volume confirm) |
| volatility | PARTIAL (ATR-based) |
| true multi-TF chart frames 5M/15M/30M | PARTIAL (`technical/mtf.py` groups by sequence, not exchange calendar) |

**Overall:** IMPLEMENTED (breadth) / PARTIAL (TF realism)

### AI

| Item | Status |
|------|--------|
| model (ML/LLM) | MISSING |
| prompt | MISSING |
| feature engineering | PARTIAL (factors + indicators) |
| prediction | PARTIAL (heuristic horizons) |
| confidence | PARTIAL (heuristic 0–100) |
| scoring | IMPLEMENTED |
| model selection | MISSING / PARTIAL (champion on prediction grades only) |

**Overall:** PARTIAL — **not** a neural/LLM AI

### TRADING SIGNALS / PLAN

| Item | Status |
|------|--------|
| BUY / STRONG BUY / SELL / STRONG SELL / WAIT / WATCH / NO_TRADE | IMPLEMENTED (`decide_matrix`) |
| trade plan entry/stop/targets | IMPLEMENTED (`trade_plan/engine.py`) |
| trailing stop | PARTIAL (helpers in `profit/protection.py`; not wired to execution) |

### RISK

| Item | Status |
|------|--------|
| position sizing | IMPLEMENTED |
| max loss / daily loss | IMPLEMENTED |
| weekly loss | PARTIAL (proxy) |
| drawdown | PARTIAL (not true peak equity history) |
| exposure / sector | PARTIAL |
| correlation | PARTIAL (book awareness, not hard risk sum) |
| kill switch | IMPLEMENTED |

**Overall:** PARTIAL

### EXECUTION / BROKER

| Item | Status |
|------|--------|
| broker API (real) | MISSING |
| paper order create/fill | IMPLEMENTED |
| order status / partial / cancel / retry | MISSING / STUB |

**Overall:** PARTIAL (paper only)

### PORTFOLIO

| Item | Status |
|------|--------|
| positions, avg cost, PnL | IMPLEMENTED (`portfolio/ledger.py`) |
| realized / unrealized | PARTIAL / IMPLEMENTED (ledger fields) |

**Overall:** IMPLEMENTED (paper) — DUPLICATED with companion

### FAVORITES / PREDICTION / NOTIFICATIONS / UI

| Module | Status |
|--------|--------|
| Favorites | IMPLEMENTED |
| Prediction tracking | PARTIAL (real eval math on often-sim prices) |
| Notifications | PARTIAL (in-app real; push/SMS stubs) |
| UI | IMPLEMENTED (mobile daily dashboard) — DUPLICATED across 3 UIs |

---

## 4. CODE DUPLICATION ANALYSIS

| # | File A | File B | What | Similarity | Suggested merge (DO NOT APPLY) |
|---|--------|--------|------|------------|--------------------------------|
| 1 | `signals/engine.py:build_trade_plan` | `trade_plan/engine.py:build_ai_trade_plan` | Entry/stop/targets | HIGH | Keep AITradePlan; retire legacy or wrap only |
| 2 | `profit/ev.py:decide_matrix` | `engines/*` + `ai/ensemble.py` | BUY decisions | MED-HIGH | Single decision authority |
| 3 | `risk.evaluate_entry` size | `trade_plan.size_from_risk` + `portfolio.size_position` | Sizing | MED | One sizing API |
| 4 | `data/providers.SimulatedProvider` | `companion/app/market.py` | Fake prices | HIGH | Delete companion or share provider |
| 5 | `portfolio/ledger.py` | `companion/app/portfolio.py` | SQLite books | HIGH | One ledger |
| 6 | `dashboard/static` | `companion/static` + `borsa_app` | UIs | MED | One client |
| 7 | `alpha.engine` votes | `strategy.modules` votes | Ensembles | MED | Unify vote bus |
| 8 | `config.models.TimeHorizon` | `prediction.models.TimeHorizon` | Enums | MED | Namespace clearly |
| 9 | `signals.compose_scores` | inline scoring in `service.scan` | Score bundle | HIGH | Dead compose path |
| 10 | AL/SAT aliases vs BUY/SELL | throughout | Signal enums | MED | Canonical English + map at edge |

---

## 5. DEAD CODE ANALYSIS

| Symbol / Module | Verdict |
|-----------------|---------|
| `signals.compose_scores` | POSSIBLY UNUSED (scan builds scores inline) |
| `signals.decide_from_scores` | POSSIBLY UNUSED |
| `ai.quality.classify_news_sentiment_stub` | POSSIBLY UNUSED |
| `engines.day_trading.opening_range_break` | POSSIBLY UNUSED |
| `walk_forward.oos_live_gate` | POSSIBLY UNUSED |
| `analytics.post_trade` | POSSIBLY UNUSED (outside tests) |
| `profit.protection` update helpers | POSSIBLY UNUSED in live execution path |
| `CalibrationMonitor.record()` | CONFIRMED UNUSED in production path (haircut stays 0) |
| `DayTradingRiskState.register_trade` | CONFIRMED UNUSED vs fills |
| `settings.favorite_scan_boost` | POSSIBLY UNUSED |
| `strategy/service._last_favorite_scan_ts` | POSSIBLY UNUSED |
| Compatibility shims (`sector/engine`, `strategy/signal_engine`, `paper_trading/service`) | POSSIBLY UNUSED / thin re-exports |

---

## 6. AI LOGIC AUDIT — direct answers

1. **Which data?** OHLCV bars, indicators, factors, regime, MTF, price action, universe flags, stub/synthetic news & fundamentals, alpha/strategy votes, opportunity EV/p_win.  
2. **Indicators?** Broad set from `indicators/engine.py` (RSI/MACD/EMA/ATR/BB/ADX/Stoch/VWAP/…).  
3. **Timeframes?** Main scan uses ~15m-like synthetic bars; MTF aggregates by index groups; engines claim long/swing/day; dashboard focus INTRADAY labels.  
4. **BUY where?** `profit/ev.py:decide_matrix` (primary), then risk/plan may demote.  
5. **STRONG BUY where?** Same `decide_matrix` when final≥90, p_win≥0.62, EV>0.8, risk≤35, liquidity≥60. Dashboard may demote if confirmation_score<70.  
6. **Confidence?** `assess_signal_quality` → **0–100 heuristic**.  
7. **Real probability?** **No.** Separate `p_win` is also heuristic (`estimate_p_win`).  
8. **What does % mean?** Display confidence / stated forecast probability — **not** guaranteed win rate.  
9. **Calibrated online?** Prediction module computes calibration buckets **after** outcomes; decision-time confidence is **not** auto-recalibrated (`CalibrationMonitor.record` unused).  
10. **Re-analyzed?** Yes — every dashboard/daily poll re-scans all symbols; favorites also get deeper analysis.  
11. **Multiple ML models?** **No.** Multiple rule “specialists” / horizon engines.  
12. **Combined how?** Weighted score bundle + alpha bias + strategy votes → `decide_matrix`. Multi-horizon API uses separate ensemble.  
13. **Prompt?** **None.**  
14. **Hallucination control?** N/A for LLM; integrity layer prevents labeling sim as live; news unavailable stays unavailable.  
15. **Look-ahead?** Main scan uses past bars only. Backtest “lookahead assert” is weak. Prediction eval uses current price at poll time, not exact horizon close. Trade-plan path outcome uses one price as high and low.

**LOOK-AHEAD BIAS:** Not proven in main live scan path; **PARTIAL risk** in backtest/WF/prediction evaluation methodology.

---

## 7. SIGNAL ENGINE AUDIT

**Primary decision tree** (`decide_matrix`):

```
KILL_SWITCH / CAPITAL_PROTECTION / EV≤min / opp=None → NO_TRADE
news_block OR conflict → WAIT (or WATCH if owned)
owned + sell_pressure ≥ sell+10 → STRONG_SELL
owned + sell_pressure ≥ sell → SELL
owned → WATCH
STRONG_BEAR → NO_TRADE
HIGH_RISK without (final≥90 & EV>1 & p_win≥0.6) → NO_TRADE

final≥90 & p_win≥0.62 & EV>0.8 & risk≤35 & liquidity≥60 → STRONG_BUY
final≥80 & EV>0 & RR≥1.5 & market≥45 → BUY
final≥65 → WATCH
final<40 → NO_TRADE
else → WAIT
```

**Thresholds (settings defaults):** buy 80, strong 90, watch 65, sell 75, min RR 1.5.

**Risk gate after signal:** Yes — `RiskEngine.evaluate_entry` can REJECT/REDUCE/WAIT.  
**Trade plan after:** `build_ai_trade_plan` can force NO_TRADE / WAIT on validation/chase.

**Post-UI demotion:** `dashboard/daily.py` confirmation_score & SIGNAL_TTL.

---

## 8. TRADE PLAN AUDIT

| Component | Source | Function |
|-----------|--------|----------|
| Entry zone | `trade_plan/engine.py` | `entry_zone_buy`, `breakout_trigger` |
| Stop | same | `compute_stop` (ATR + structure) |
| Targets T1–T3 | same | `compute_targets` |
| R/R | same | `plan_expectancy` / plan fields |
| Position size | `size_from_risk` + risk engine quantity | Also `portfolio.construction.size_position`, `dynamic_size_multiplier` |
| Legacy plan | `signals/engine.py:build_trade_plan` | Still called in scan before AI plan |
| Chase / invalid zone | `assess_chase`; UI `plan_invalid` in `daily.py` | |

Plan ≠ order (documented and mostly enforced).

---

## 9. LIVE DATA AUDIT

| Question | Answer |
|----------|--------|
| Provider | Default `SimulatedProvider` |
| Real BIST/broker feed | **No working implementation** |
| WebSocket | **No** |
| REST live | Stub `HttpLiveProviderStub` — stays disconnected |
| Polling | Yes (scan tick + UI 15s) |
| Cache | In-memory bars |
| Fallback | `RequiredLiveProvider` → no prices (fail closed) |
| Freshness / stale | Yes (`data/integrity.py`) |
| Market open/close | Approximate BIST hours |
| Can fake prices show as live? | **borsa_bot UI: No** (labeled SİMÜLE / VERİ YOK). **companion: risk of confusion** (sim prices, weaker banners). |

---

## 10. BROKER AUDIT

| Capability | Status |
|------------|--------|
| Auth / real account / positions sync | MISSING |
| Order create | Paper only (`PaperBroker.submit`) |
| Fill | Immediate synthetic fill |
| Partial / cancel / reject/retry/timeout | MISSING / minimal reject reasons |
| LIVE | Blocked in execute_signal, risk, safety, paper, API |

**Chain:** Signal → (optional approved bool) → re-scan → SafetyGate → RiskEngine → PaperBroker → Ledger → alerts.

**Note:** `approved=true` is a caller boolean, not a cryptographic/secure approval ticket.

---

## 11. RISK ENGINE AUDIT

| Control | Status |
|---------|--------|
| max position / sizing | IMPLEMENTED |
| max daily loss | IMPLEMENTED |
| max drawdown | PARTIAL |
| weekly loss | PARTIAL |
| stop loss validation | IMPLEMENTED |
| exposure / sector count | PARTIAL |
| correlation hard limit | PARTIAL |
| kill switch | IMPLEMENTED |
| broker failure | PARTIAL (assumed ok) |
| data failure | IMPLEMENTED (stale/required blocks) |
| day trade limits module | PARTIAL (disconnected from fills) |

---

## 12. BACKTEST AUDIT

| Item | Status |
|------|--------|
| Historical real data | MISSING (uses SimulatedProvider seed) |
| Costs/slippage/commission | PARTIAL (configured; simplistic) |
| Spread/latency realism | MISSING / weak |
| Survivorship | MISSING |
| Look-ahead control | WEAK (`assert_no_lookahead` trivial) |
| Train/test / walk-forward | ILLUSTRATIVE — not true OOS |
| Monte Carlo API | Hard-coded sample PnLs |

**Backtest ≠ live performance:** Disclaimers exist; UI must not treat as live equity proof. **PARTIAL / CRITICAL for claims.**

---

## 13. PREDICTION ACCURACY AUDIT

| Question | Answer |
|----------|--------|
| Horizons 1H/3H/1D/3D/1W recorded? | **Yes** (immutable SQLite) |
| Compared to actual price? | **Yes, when due** — but “actual” is usually **simulator** price |
| Direction accuracy / return error / quality score | Yes |
| Calibration buckets / Brier / grades | Yes, from stored evaluations |
| Rating from real BIST? | **Not currently** — from whatever provider is configured |
| Is accuracy just AI self-claim? | **No** for rating math — but inputs are often simulated outcomes |

---

## 14. FAVORITES AUDIT

| Feature | Status |
|---------|--------|
| Button / DB / groups / notes / priority | IMPLEMENTED |
| Dashboard ordering | IMPLEMENTED (favorites-first within signal strength rules) |
| Scan order | **Yes — favorites scanned first** |
| Alerts / price alerts | IMPLEMENTED (in-app) |
| Auto-BUY from favorite | **No** (principle enforced) |

---

## 15. NOTIFICATION AUDIT

| Channel | Reality |
|---------|---------|
| In-app inbox | REAL (SQLite) |
| Push | PLACEHOLDER / stub |
| Sound | Intent only (browser may play separately) |
| TTS | Text intent; browser `speechSynthesis` was in older UI; current daily UI limited |
| SMS | Null / log / HTTP stub — not production |

Events covered in bridge: BUY/SELL signals, stops/targets (via monitor), kill switch, risk, orders, favorite signals.

---

## 16. DATABASE AUDIT

Runtime SQLite (created lazily):

| DB | Tables |
|----|--------|
| `paper.db` | account, positions, trades, decision_log |
| `predictions.db` | predictions, prediction_evaluations, forecast_revisions, trade_plan_outcomes |
| `favorites.db` | favorites, groups, members, price_alerts, events, signal_stats |
| `notifications.db` | notification_log, in_app_inbox |
| companion `borsa.db` | account, positions, trades |

JSON: `notification_settings.json`.

**Duplicate:** companion ledger vs paper ledger.

---

## 17. API AUDIT (`borsa_bot/dashboard/app.py`)

| Method | Endpoint | Used by UI? |
|--------|----------|-------------|
| GET | `/api/health` | indirect via daily/dashboard |
| GET | `/api/dashboard` | YES |
| GET | `/api/daily` | YES (primary) |
| POST | `/api/execute` | POSSIBLY (removed from new main cards; still API) |
| POST | `/api/reset` | POSSIBLY unused in new UI |
| GET | `/api/backtest` | NO (new UI) |
| GET | `/api/opportunities` | NO |
| GET | `/api/daily-report` | NO |
| GET | `/api/walk-forward` | NO |
| GET | `/api/monte-carlo` | NO |
| GET | `/api/multi-horizon` | NO (old UI used) |
| GET | `/api/ai-daily-report` | NO |
| GET/POST/PUT | `/api/notifications*` | PARTIAL / older UI |
| GET | `/api/symbol/{symbol}` | YES |
| GET | `/api/trade-plan/{symbol}` | POSSIBLY |
| GET/POST/PUT | `/api/favorites*` | YES (toggle) |
| GET/POST | `/api/predictions*` | YES (report) |
| GET | `/` | YES |

**Auth:** NONE on all endpoints.

---

## 18. FRONTEND AUDIT

Single file: `dashboard/static/index.html` (~393 lines).

| Screen | API |
|--------|-----|
| Home daily sections | `GET /api/daily` |
| Portfolio / system health | `GET /api/dashboard` |
| Detail | `GET /api/symbol/{symbol}` |
| Favorite toggle | `POST /api/favorites/{symbol}/toggle` |
| AI performance panel | `GET /api/predictions/report` |

**Charts:** MISSING (no chart library).  
**Mobile:** YES (bottom nav, large labels).  
**Business logic in UI:** Light filtering/sorting only; decisions from API.

---

## 19. SECURITY AUDIT

| Check | Result |
|-------|--------|
| Hardcoded live broker secrets in tracked source | **NOT FOUND** |
| `.env` local secrets | Present locally / gitignored pattern — treat carefully |
| API authentication | **MISSING** |
| Authorization | **MISSING** |
| Open execute/reset without auth | **FOUND (design risk)** |
| Secret scrubbing in alerts | Present in alert tests/paths |

---

## 20. ERROR HANDLING

| Failure | Behavior |
|---------|----------|
| No market data | scan returns []; UI VERİ YOK; execute blocked |
| Stale data | signals paused / execute blocked |
| LIVE mode | hard reject |
| Alert channel failure | isolated (does not halt trading) |
| AI timeout | N/A (sync heuristics) |
| DB errors | largely unhandled beyond sqlite defaults |
| DATA FAILURE → NO TRADE | **YES** for required/stale paths |

---

## 21. TEST COVERAGE

| Type | Present? |
|------|----------|
| Unit | YES (`tests/test_*.py`, 71 tests historically green) |
| Integration | PARTIAL (TradingService dashboard/scan) |
| E2E / browser | MISSING |
| Backtest tests | PARTIAL (synthetic) |
| Coverage % | Not measured this audit (no coverage run per no-change rule) — **ESTIMATE weak–moderate ~30–45% critical paths** |

Critical gaps: auth, real provider, concurrency, exact horizon marks, partial exits, companion safety.

---

## 22. DEPENDENCY AUDIT

`borsa_bot/requirements.txt`:

| Package | Purpose | Used? | Critical? |
|---------|---------|-------|-----------|
| fastapi | API | YES | YES |
| uvicorn | server | YES | YES |
| python-dotenv | env | YES | YES |
| pytest | tests | YES | YES |

No numpy/pandas/sklearn/torch/broker SDK/httpx in main bot requirements.  
**No updates recommended in this audit.**

---

## 23. PERFORMANCE AUDIT

| Issue | Severity |
|-------|----------|
| Full universe rescan on every `/api/daily` + `/api/dashboard` | HIGH |
| `tick()` mutates sim prices on every scan | MED |
| Duplicate dashboard+daily fetches from UI | MED |
| Prediction insert throttle 15m helps | — |
| GET dashboard side effects (exits, predictions, alerts) | HIGH design smell |
| No websocket; 15s polling | OK for paper |

---

## 24. ARCHITECTURE PROBLEMS

- **God class:** `TradingService` (~1180 lines)  
- **Duplicated decision engines**  
- **3 UIs / 2 paper ledgers**  
- **Business-ish assembly in `daily.py` (OK) vs thin UI**  
- **Synthetic fundamentals affect scores when simulated**  
- **Tight coupling:** scan owns everything  
- **No circular imports found as hard failure** (compatibility shims exist)

---

## 25. CODE QUALITY SCORES (0–100)

| Module | Score |
|--------|------:|
| Market Data | 55 |
| Technical Analysis | 80 |
| AI | 43 |
| Signals | 54 |
| Trade Plan | 72 |
| Risk | 65 |
| Execution | 45 |
| Portfolio | 57 |
| Favorites | 73 |
| Prediction Tracking | 59 |
| Notifications | 55 |
| Frontend | 62 |
| Tests | 52 |

---

## 26. TRADING SAFETY SCORE

| Criterion | Score |
|-----------|------:|
| Live Data Integrity | 12/15 |
| Risk Management | 13/20 |
| Execution Safety | 5/15 |
| Error Handling | 5/10 |
| Testing | 4/10 |
| Backtest Integrity | 3/10 |
| AI Reliability | 4/10 |
| Broker Safety (LIVE block) | 12/15 |
| **TOTAL** | **≈58/100** |

**Paper demo: usable. Live automated trading: NOT READY.**

---

## 27. MOST CRITICAL PROBLEMS (Top 10)

### CRITICAL #1
**Problem:** No real live market data or broker.  
**Why:** Cannot be a live trading system.  
**Files:** `data/providers.py`, `execution/paper.py`  
**Risk:** User mistakes paper for live.  
**Suggested:** Wire licensed feed + broker; keep fail-closed.

### CRITICAL #2
**Problem:** Unauthenticated APIs including execute/reset.  
**Why:** Anyone with network access can trade paper / mutate state.  
**File:** `dashboard/app.py`  
**Risk:** Abuse / accidental wipe.  
**Suggested:** AuthN/AuthZ before any mutate route.

### CRITICAL #3
**Problem:** `approved=true` is not secure approval.  
**File:** `strategy/service.py:execute_signal`  
**Risk:** False sense of control.  
**Suggested:** Server-side pending approval tokens.

### CRITICAL #4
**Problem:** Backtest/walk-forward are synthetic / non-OOS.  
**Files:** `backtest/runner.py`, `walk_forward/runner.py`  
**Risk:** False performance confidence.  
**Suggested:** Real history + honest labeling only.

### CRITICAL #5
**Problem:** “AI” confidence is heuristic, not calibrated probability.  
**Files:** `ai/quality.py`, `profit/ev.py`  
**Risk:** Users read % as win odds.  
**Suggested:** Keep dual labels; calibrate offline; never claim guarantee.

### CRITICAL #6
**Problem:** Multiple conflicting signal engines.  
**Files:** `profit/ev.py`, `engines/*`, `ai/ensemble.py`, `signals/engine.py`  
**Risk:** Unpredictable product behavior.  
**Suggested:** Single decision authority.

### CRITICAL #7
**Problem:** God orchestrator `TradingService.scan`.  
**File:** `strategy/service.py`  
**Risk:** Untestable / unsafe changes.  
**Suggested:** Split pipeline stages (later).

### CRITICAL #8
**Problem:** Exit management incomplete (poll-only; T1/stop full exit; trailing unused).  
**Files:** `strategy/service.py` monitor_exits, `profit/protection.py`  
**Risk:** Paper PnL ≠ stated plan.  
**Suggested:** Wire plan lifecycle.

### CRITICAL #9
**Problem:** Companion app bypasses main risk/integrity stack.  
**Path:** `companion/`  
**Risk:** Parallel unsafe paper path.  
**Suggested:** Deprecate or hard-gate.

### CRITICAL #10
**Problem:** GET endpoints mutate market/predictions/alerts.  
**Files:** `dashboard/app.py`, `strategy/service.py`  
**Risk:** Non-idempotent reads; TTL refresh artifacts.  
**Suggested:** Separate read vs scan jobs.

---

## 28. STABLE MODULES (prefer not to casually refactor)

- `indicators/engine.py` — solid TA set  
- `data/integrity.py` — provenance honesty  
- `favorites/store.py` + priority principles  
- `trade_plan/engine.py` core math (entry/stop/targets)  
- `alerts/` channel isolation pattern  
- `prediction/store.py` immutability  
- LIVE hard-blocks across risk/safety/paper/API  
- Metric distinction TAHMİN OLASILIĞI ≠ GEÇMİŞ DOĞRULUK  

---

## 29. REFACTOR BACKLOG (do not apply now)

| Priority | Item |
|----------|------|
| P0 | Real data provider + keep fail-closed |
| P0 | API auth |
| P0 | Single decision engine |
| P1 | Split `TradingService` |
| P1 | Retire legacy trade plan / dead score paths |
| P1 | Wire exits/trailing to plan |
| P1 | Deprecate/isolate companion |
| P2 | True OOS backtest |
| P2 | Calibration feedback into confidence |
| P2 | Reduce scan-on-GET side effects |
| P3 | UI polish / charts |
| P3 | Enum cleanup AL/SAT |

---

## 30. CODE REDUCTION OPPORTUNITY (ESTIMATE)

| Bucket | ESTIMATE |
|--------|----------|
| Necessary core | ~55–65% of borsa_bot |
| Duplicative | ~15–25% |
| Dead / compatibility | ~5–10% |
| Docs/reports outside bot | large but non-runtime |
| Safe deletion without design work | **LOW** — need ownership decisions first |

Do **not** mass-delete without your approval.

---

## 31. FINAL ARCHITECTURE DIAGRAM (ACTUAL)

```
                    ┌─────────────────────┐
                    │  SimulatedProvider  │◄── default
                    │  RequiredLive (no)  │
                    │  HttpLiveStub (no)  │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │  TradingService     │  GOD ORCHESTRATOR
                    │  scan() / execute() │
                    └──────────┬──────────┘
         ┌─────────────┬───────┼───────┬─────────────┐
         ▼             ▼       ▼       ▼             ▼
   Indicators     Factors   Regime  Alpha/Votes   News/Fund*
         └─────────────┴───────┬───────┴─────────────┘
                               ▼
                      ScoreBundle + EV/p_win
                               ▼
                         decide_matrix
                               ▼
                          RiskEngine
                               ▼
                       AITradePlan engine
                               ▼
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
         Prediction       Favorites         Alerts
         (measure)        (priority)        (notify)
              ▼                ▼                ▼
         SQLite DBs ◄──────────┴──── PortfolioLedger
                               ▼
                      FastAPI /api/daily
                               ▼
                      Mobile Dashboard UI

Parallel (weaker): companion/  |  Flutter borsa_app/
Parallel (analysis only): engines/orchestrator + multi-horizon API
```

\*News usually unavailable; fundamentals synthetic under simulated provider.

---

## 32. FINAL SUMMARY

```
PROJECT:           ~13.5k LOC core borsa_bot (.py+.html); broader repo larger
ARCHITECTURE:      NEEDS WORK
LIVE DATA:         MOCK (default) / PARTIAL integrity layer
AI:                PARTIAL (heuristics, not ML)
RISK:              PARTIAL
EXECUTION:         PARTIAL (paper) / CRITICAL if claimed live
BACKTEST:          CRITICAL (synthetic / weak OOS)
PREDICTION TRACKING: PARTIAL (good plumbing; sim outcomes)
FAVORITES:         GOOD
NOTIFICATIONS:     PARTIAL
TESTING:           PARTIAL
SECURITY:          NEEDS WORK (no auth)
OVERALL:           58 / 100
```

---

## 33. NEXT STEP (max 10 recommendations — no code yet)

1. Decide **single product surface**: keep `borsa_bot`, freeze/deprecate `companion` + clarify `borsa_app`.  
2. Choose **real market-data vendor** and credentials strategy; keep REQUIRED fail-closed until connected.  
3. Add **API authentication** before any further feature work.  
4. Declare **one decision authority** (`decide_matrix` vs engines) and document the rest as non-exec.  
5. Inventory **dead paths** (`compose_scores`, unused protection/day_limits wiring) for approved deletion.  
6. Separate **read APIs** from **scan/tick jobs**.  
7. Define **LIVE READY checklist owners** (data, broker, risk, tests).  
8. Replace synthetic backtest claims with **honest “illustrative only”** product policy (already partly true).  
9. Plan **exit lifecycle** (partial TP, trailing) only after data/broker plan.  
10. After you review this report, pick a **P0 slice** (data XOR auth XOR decision unification) — not all at once.

---

*End of audit. No application code was modified for this report.*
