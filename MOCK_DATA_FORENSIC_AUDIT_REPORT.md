# PHASE 1 — MOCK DATA FORENSIC AUDIT REPORT

**Date:** 2026-08-11  
**Scope:** `/workspace/borsa_bot` (primary), `/workspace/companion` (secondary)  
**Rule:** Read-only analysis. No code changes, no new providers, no refactors.

---

## 1. ALL DATA SOURCES FOUND

### A. Price / OHLCV generators (non-market)

| Source | File | Mechanism | Severity |
|--------|------|-----------|----------|
| **SimulatedProvider** | `borsa_bot/data/providers.py` L45–149 | `random.Random(seed)` walk from hardcoded `UNIVERSE` bases; `_init_history` 240 bars; `tick()` appends new bar | **CRITICAL** |
| **UNIVERSE base prices** | same L20–32 | Hardcoded seed prices (e.g. THYAO 312.5) | **CRITICAL** (seed for all sim prices) |
| **RequiredLiveProvider** | same L152–198 | No prices; `get_quote` raises; `has_market_data()=False` | Fail-closed (good) — not mock fill |
| **HttpLiveProviderStub** | same L201–263 | Never fetches; stays disconnected; **explicitly does not fall back to simulated** (L223–230) | Not producing prices today |
| **companion market** | `companion/app/market.py` | Separate `random` walk from `_SEED` prices | **CRITICAL** (if companion used) |

### B. Non-price synthetic inputs that feed decisions

| Source | File | What | Severity |
|--------|------|------|----------|
| `_FAKE` fundamentals | `fundamental/provider.py` L8–14, L17–28 | Hardcoded PE/ROE/… when `DATA_PROVIDER=simulated` | **HIGH** |
| `latest_stub_headline` | `news/analyzer.py` L68–70 | Always `None` → news unavailable neutral score 50 | **MEDIUM** (no fake headlines) |
| Prediction forecasts | `prediction/forecast.py` | Heuristic ATR/momentum/EV → MODEL_FORECAST | **HIGH** (forecasts) |
| Monte Carlo sample | `dashboard/app.py` L119–120 | Hardcoded PnL list `[1200, -800, …]` | **LOW** (API toy) |
| Strategy ranking constants | `strategy/ranking.py` | Illustrative historical stats | **LOW** |
| Alert test endpoint | `dashboard/app.py` `test_notification` | Synthetic alert event | **LOW** |
| Backtest/WF | `backtest/runner.py`, `walk_forward/runner.py` | `SimulatedProvider(seed=…)` | **HIGH** if mistaken for live proof |

### C. Keyword hits (behavioral, not exhaustive)

Found in code: `simulated`, `SIMULATED`, `synthetic`, `fake` (`_FAKE`), `stub`, `placeholder` (UI search + HTTP stub note), `random`, `demo` (UI banner), `sample` (monte carlo / sample tiers), `paper`.

No working Yahoo/BIST/broker HTTP fetch producing live quotes was found in runtime path.

---

## 2. PRICE DATA FLOW (actual code)

```
DATA SOURCE
  File: data/providers.py
  Class: SimulatedProvider (default via create_provider)
  Type: fabricated OHLCV + QuoteSnapshot
  Config: DATA_PROVIDER=simulated (.env / settings default)
        ↓
DATA FETCH
  File: strategy/service.py → TradingService.scan / tick
  Functions: provider.tick(), get_quote(symbol), get_bars(symbol, n)
  Type: QuoteSnapshot.price, Bar OHLCV
        ↓
NORMALIZATION
  Status: NONE dedicated
  Spreads invented in get_quote: spread = max(0.01, close * 0.0008)
        ↓
CACHE
  Status: in-memory only (_bars dict on SimulatedProvider)
  No Redis/disk market cache; SQLite stores decisions/predictions/fills AFTER
        ↓
INDICATORS
  File: indicators/engine.py → compute_indicators(bars)
  Type: IndicatorSet (RSI, MACD, ATR, …) CALCULATED from sim bars
        ↓
SIGNAL / SCORE / AI HEURISTICS
  Files: signals/engine.py, ai/quality.py, alpha/engine.py,
         factors/engine.py, profit/ev.py (decide_matrix)
  Type: scores, p_win, SignalAction — all driven by sim inputs
        ↓
TRADE PLAN
  Files: signals/engine.py:build_trade_plan,
         trade_plan/engine.py:build_ai_trade_plan
  Type: entry/stop/T1–T3 from sim price + ATR
        ↓
RISK / PAPER EXEC
  risk/engine.py, execution/paper.py, portfolio/ledger.py
  Type: paper fills at sim marks
        ↓
PREDICTION TRACKING
  prediction/* — forecasts from sim; “actual” = provider.get_quote later
        ↓
FRONTEND
  dashboard/daily.py → /api/daily → static/index.html
  Labels: SİMÜLE FİYAT (not CANLI) when kind=SIMULATED
```

| Stage | File | Function | Data type | Source |
|-------|------|----------|-----------|--------|
| Source | `data/providers.py` | `SimulatedProvider._init_history/tick` | Bar/Quote | MOCK |
| Fetch | `strategy/service.py` | `scan()` | QuoteSnapshot | MOCK |
| Indicators | `indicators/engine.py` | `compute_indicators` | IndicatorSet | CALCULATED←MOCK |
| Decision | `profit/ev.py` | `decide_matrix` | SignalAction | CALCULATED←MOCK |
| Plan | `trade_plan/engine.py` | `build_ai_trade_plan` | AITradePlan | CALCULATED←MOCK |
| UI | `dashboard/daily.py` | `simplify_card` | card JSON | MOCK labeled |

---

## 3. MOCK DATA SEVERITY CATALOG

| Item | Severity | Why |
|------|----------|-----|
| SimulatedProvider OHLCV/price/volume | **CRITICAL** | Entire trading pipeline input |
| UNIVERSE hardcoded bases | **CRITICAL** | Seeds all sim prices |
| companion `_SEED` / `_tick` | **CRITICAL** | Independent paper trading prices |
| Synthetic fundamentals `_FAKE` | **HIGH** | Blended into `ScoreBundle.fundamental` → decisions |
| Indicator/RSI/MACD etc. | **HIGH** | Pure functions of mock OHLCV |
| AI confidence / p_win / decide_matrix | **HIGH/CRITICAL** | Decisions from mock |
| Trade plan entry/stop/target | **HIGH** | From mock price+ATR |
| Prediction forecast + “actual” eval | **HIGH** | Accuracy vs simulator, not BIST |
| paper.db fills / marks | **HIGH** | Accounting on mock marks |
| predictions.db evaluations | **HIGH** | Mixed trust if later real data added without namespace |
| News stub (None) | **MEDIUM** | Neutral; does not invent headlines |
| UI price display of sim | **MEDIUM** | Shown with SİMÜLE banner (honesty OK) |
| Monte Carlo hardcoded sample | **LOW** | Demo endpoint |
| Notification test event | **LOW** | Dev helper |
| Tests using SimulatedProvider | **LOW** | Test-only |

---

## 4. REAL EXTERNAL DATA CONSUMERS

**Finding: none in the active default runtime path.**

| Candidate | Status |
|-----------|--------|
| `HttpLiveProviderStub` | Scaffold only — `tick()` sets `_connected=False`, note `LIVE_ADAPTER_NOT_IMPLEMENTED` |
| Broker HTTP | No live broker client |
| KAP/news HTTP | `latest_stub_headline` returns `None` |
| Push/SMS HTTP | Stubs / null providers |

Therefore: **Provider / Endpoint / Auth / Frequency — N/A (no live feed operational).**

Env hooks that *would* matter later (no secrets printed):

- `MARKET_DATA_URL`
- `MARKET_DATA_TOKEN`
- `DATA_PROVIDER=live|required|simulated`

---

## 5. FALLBACK ANALYSIS

### Default: `DATA_PROVIDER=simulated`

```
[ALWAYS MOCK]
→ tick generates new bar
→ scan uses it
→ signals generated
No “real failure → mock” because real was never attempted.
```

### `DATA_PROVIDER=required` or `live` without credentials

```
RequiredLiveProvider
→ has_market_data() = False
→ scan() returns [] early (strategy/service.py)
→ execute blocked ("DATA SOURCE REQUIRED")
→ UI: VERİ YOK / NO_DATA cards
→ Does NOT fall back to SimulatedProvider
```

### `DATA_PROVIDER=live` with URL+token but stub unimplemented

```
HttpLiveProviderStub.tick()
→ connected stays False
→ get_quote raises NO_MARKET_DATA
→ Explicit comment: Do NOT fall back to simulated prices
```

### Stale simulated

```
If age > DATA_FRESHNESS_SEC without tick:
→ freshness STALE
→ daily.py may pause actionable signals / strip cards
BUT: scan() always calls tick() first → sim rarely becomes stale in practice
```

**Answer to key question:**  
When configured for live/required and data fails, system **does not** currently substitute mock prices.  
When configured for simulated (default), **all** prices are mock by design — and they **do** drive signals.

---

## 6. STALE DATA

| Control | Present? | Where |
|---------|----------|-------|
| Timestamp on quotes/bars | Yes | `QuoteSnapshot.ts`, `Bar.ts` |
| Data age | Yes | `data/integrity.py:age_seconds` |
| Stale threshold | Yes | `settings.data_freshness_sec` (default 30) |
| Market session | Partial | `bist_session_now` approx hours; no holidays |
| Missing timestamp | Handled | → NO_DATA / note |

**Can 30-minute-old data show as LIVE?**

- For **SIMULATED**: price_label becomes `SİMÜLE (ESKİ)` or freshness `STALE` — **never** `CANLI FİYAT` (`integrity.py` L121–128 vs L129–135).
- For **real LIVE kind** (not operational today): only if `age <= max_age_sec` → freshness `LIVE` and `is_live_market=True`. If age exceeds threshold → `STALE`, `is_live_market=False`.

**Caveat:** Simulated path treats `FRESH_SIMULATED` as “fresh enough” for paper safety (`health()` L115–120), so sim trading continues — labeled sim, not live.

---

## 7. SIGNAL SAFETY

### If market data is NOT real (`SimulatedProvider`)

**YES — BUY / STRONG_BUY / SELL / STRONG_SELL can be produced.**

| | |
|--|--|
| File | `strategy/service.py` |
| Flow | `tick()` → indicators → `decide_matrix` → risk → trade plan |
| Decision | `profit/ev.py:decide_matrix` |
| Risk | Users may trade paper on fantasy prices; if banners ignored, false confidence |

Evidence: default `.env` `DATA_PROVIDER=simulated`; `scan()` does not refuse sim; only refuses `has_market_data()==False`.

### If market data missing (`RequiredLiveProvider`)

**NO signals** — empty scan; UI NO_DATA; execute blocked.

### If STALE (daily assembly)

Actionable decisions demoted toward WAIT when `signals_paused` (`dashboard/daily.py`).

---

## 8. FRONTEND DATA AUDIT

Source: `/api/daily` + `/api/dashboard` + `/api/symbol/{id}` ← all from `TradingService` + provider.

| UI field | Status (default config) |
|----------|-------------------------|
| PRICE | **MOCK** (labeled SİMÜLE FİYAT) |
| CHANGE | **CALCULATED** from mock bars |
| VOLUME | **MOCK** (not shown prominently on main card) |
| RSI / MACD | **CALCULATED←MOCK** (detail/indicators path) |
| SIGNAL | **CALCULATED←MOCK** |
| CONFIDENCE (AI Güven) | **CALCULATED** heuristic |
| ENTRY / STOP / TARGET | **CALCULATED←MOCK** |
| AI FORECAST | **CALCULATED** heuristic MODEL_FORECAST |
| Geçmiş doğruluk | **CALCULATED** from prediction DB (usually sim actuals) |
| Haber / KAP | **UNAVAILABLE** (honest empty) |

UI integrity banner explicitly says sim ≠ live when `kind===SIMULATED` (`index.html`).

---

## 9. DATABASE AUDIT

| DB | What’s stored | Provenance today |
|----|---------------|------------------|
| `paper.db` | account, positions, trades, decision_log | Prices/fills from **sim** marks |
| `predictions.db` | forecasts + evaluations + outcomes | Forecasts heuristic; **actual_price from provider** (= sim) |
| `favorites.db` | watchlist metadata | Not market prices |
| `notifications.db` | alert log/inbox | May embed last sim prices in payloads |
| companion `borsa.db` | positions/trades | Separate **sim** prices |

**Mixing risk:** Tables have **no `data_source_kind` column**. If production later switches to live without DB reset/namespace, **historical sim evaluations/fills can sit beside real ones** undistinguished → **CRITICAL for prediction accuracy & paper PnL history**.

---

## 10. PREDICTION DATA

| Field | Source | Real market? |
|-------|--------|--------------|
| CURRENT / price_at_prediction | `get_quote` at record time | **No** (sim default) |
| FORECAST PRICE | `generate_horizon_forecasts` | Heuristic, not exchange |
| ACTUAL PRICE | `evaluate_due(price_lookup)` → provider quote | **Simulator price**, not BIST print |
| RETURN / ERROR | computed from above | Sim-vs-sim |
| ACCURACY / Brier / grade | from evaluations table | **Objectively computed**, but on **sim outcomes** |

**Verdict:** ACTUAL PRICE is “realized” only relative to the configured provider. Under default config it is **not** true exchange settlement.

---

## 11. TEST / PRODUCTION SEPARATION

| Switch | Role |
|--------|------|
| `MODE=PAPER` / `LIVE` | LIVE execution blocked; default PAPER |
| `DATA_PROVIDER` | `simulated` (default) / `required` / `live` |
| `ALLOW_SIMULATED_PAPER` | Setting exists |
| `live_ready` | Forced `False` in health/dashboard |
| NODE_ENV | Not used (Python app) |

**Can production accidentally use mock?**  
**YES** — if deploy uses defaults (`.env.example` / settings default `DATA_PROVIDER=simulated`). There is **no** hard refuse of simulated in “production hostname”. Safety relies on ops config + UI labels + `live_ready=false`.

---

## 12. HARDCODED VALUES (trading-impacting)

| File | Approx lines | Value | Purpose | Trading impact |
|------|--------------|-------|---------|----------------|
| `data/providers.py` | 20–32 | UNIVERSE bases e.g. 312.5, 78.4, … | Seed prices | **CRITICAL** — all paths |
| `data/providers.py` | 62–70, 89–105 | random drifts, vol `1_000_000 * …` | Generate OHLCV | **CRITICAL** |
| `data/providers.py` | 117 | `close * 0.0008` spread | Fake bid/ask | **HIGH** (spread gates) |
| `fundamental/provider.py` | 8–14 | PE/ROE/… table | Fake fundamentals | **HIGH** |
| `companion/app/market.py` | 17–28, 40–45 | `_SEED`, random drift | Companion prices | **CRITICAL** if used |
| `dashboard/app.py` | 119 | Monte Carlo sample list | Demo stats | LOW |
| `config/settings.py` | thresholds 80/90/… | Signal thresholds | Rules (not prices) | HIGH (logic) |
| `prediction/forecast.py` | scale tables | Horizon scales | Forecast shape | HIGH (forecasts) |

---

## 13. DATA INTEGRITY RATING (default deploy)

| Stream | Score | Rationale |
|--------|------:|-----------|
| Live Price | **5/100** | No live feed; sim only |
| Volume | **5/100** | Random-generated |
| OHLCV | **8/100** | Random walk, not exchange |
| Indicators | **35/100** | Math OK, inputs fake |
| Signals | **20/100** | Deterministic on fake world |
| Trade plans | **25/100** | Consistent with fake ATR/price |
| Prediction accuracy | **12/100** | Grades real math, fake actuals |
| UI provenance labeling | **75/100** | Honest SİMÜLE / VERİ YOK |
| Fail-closed on REQUIRED | **85/100** | No mock fallback |
| DB provenance isolation | **15/100** | No source column / namespace |

---

## 14. CRITICAL FINDINGS (Top 10)

### CRITICAL #1
**Problem:** Default market data is 100% simulated random-walk OHLCV.  
**File:** `data/providers.py` — `SimulatedProvider`  
**Function:** `_init_history`, `tick`, `get_quote`  
**Why critical:** Entire stack believes these prices.  
**Trading impact:** STRONG BUY/BUY/plans/paper fills all from fantasy.  
**Suggested:** Keep fail-closed; require explicit live provider before any LIVE claim (do not implement in this phase).

### CRITICAL #2
**Problem:** Mock data **does** generate trading signals.  
**File:** `strategy/service.py` + `profit/ev.py`  
**Function:** `scan` → `decide_matrix`  
**Why critical:** Signal safety does not require `is_live_market`.  
**Trading impact:** Paper (and any future misconfig) trades on mock.  
**Suggested:** Gate STRONG_BUY/BUY on `source_meta.is_live_market` for production mode.

### CRITICAL #3
**Problem:** Prediction “actual” prices are simulator quotes.  
**File:** `prediction/service.py` — `evaluate_due`  
**Why critical:** Accuracy/Brier/grades look scientific but measure sim.  
**Trading impact:** False model trust.  
**Suggested:** Tag evaluations with `data_source_kind`; separate DBs.

### CRITICAL #4
**Problem:** No DB column separating sim vs live history.  
**Files:** `predictions/store.py`, `portfolio/ledger.py`  
**Why critical:** Future live data can contaminate history.  
**Trading impact:** Corrupted calibration / PnL narrative.

### CRITICAL #5
**Problem:** Synthetic fundamentals actively score when simulated.  
**File:** `fundamental/provider.py` — `_FAKE`  
**Why critical:** Moves `ScoreBundle` → decisions.  
**Trading impact:** Biased BUY/NO_TRADE.

### CRITICAL #6
**Problem:** Production defaults allow mock (`DATA_PROVIDER` default `simulated`).  
**File:** `config/settings.py` L74; `.env` / `.env.example`  
**Why critical:** Easy to ship demo as “the bot”.  
**Trading impact:** Ops foot-gun.

### CRITICAL #7
**Problem:** Companion app independent mock market without borsa_bot integrity banners/gates.  
**File:** `companion/app/market.py`  
**Why critical:** Parallel unsafe paper path.  
**Trading impact:** Confusion / ungoverned fills.

### CRITICAL #8
**Problem:** `scan()` always `tick()`s simulator → “freshness” almost always green for sim.  
**File:** `strategy/service.py`  
**Why critical:** Stale protection weak on the only active provider.  
**Trading impact:** Freshness feels healthy while data is still fake.

### CRITICAL #9
**Problem:** Hardcoded UNIVERSE seed prices resemble plausible BIST levels.  
**File:** `data/providers.py` L20–32  
**Why critical:** Looks “real” at a glance (THYAO ~312).  
**Trading impact:** Social-engineering of trust if labels ignored.

### CRITICAL #10
**Problem:** Backtest/WF/Monte Carlo endpoints consume or invent non-market series.  
**Files:** `backtest/runner.py`, `walk_forward/runner.py`, `dashboard/app.py` monte-carlo  
**Why critical:** Performance theater.  
**Trading impact:** False edge narrative.

---

## 15. FINAL DATA FLOW (this project)

```
[HARDCODED UNIVERSE BASE PRICES]
            ↓
[SimulatedProvider random OHLCV + fake volume/spread]
            ↓
[TradingService.tick/scan]  ← also default paper path
            ↓
[indicators / factors / regime / alpha / “AI” heuristics]
            ↓
[decide_matrix → BUY / STRONG_BUY / …]
            ↓
[RiskEngine] → [AITradePlan]
            ↓
[PaperBroker + Ledger]     [PredictionStore eval vs sim quote]
            ↓
[/api/daily + UI]
   banner: SİMÜLE VERİ · CANLI PİYASA DEĞİL
   live_ready: false

ALTERNATE FAIL-CLOSED:
[DATA_PROVIDER=required|live without working feed]
            ↓
[RequiredLiveProvider / HttpLiveStub disconnected]
            ↓
[scan=[] · VERİ YOK · no signal · no execute]
            ↓
(no mock price substitution)
```

---

## 16. FINAL VERDICT

1. **Projede gerçek canlı piyasa verisi var mı?**  
   **Hayır** (çalışan runtime path’te yok).

2. **Hangi modüller mock kullanıyor?**  
   Data provider (default), indicators, signals/AI heuristics, trade plans, paper portfolio, prediction evals, fundamentals (sim mode), companion market, backtest/WF.

3. **Mock veri trading kararını etkiliyor mu?**  
   **Evet — tamamen** (default `simulated`).

4. **Gerçek veri kesilirse sistem işlem sinyali üretebilir mi?**  
   - `required`/`live` fail: **Hayır** (boş scan).  
   - Hâlâ `simulated` ise: **Evet** (zaten mock).

5. **Eski veri canlı gibi gösterilebilir mi?**  
   Sim: **CANLI diye etiketlenmez**; stale sim → SİMÜLE(ESKİ)/STALE.  
   Gerçek live kind (henüz yok): threshold aşınca STALE, LIVE değil.

6. **Prediction accuracy gerçek sonuçlarla mı?**  
   **Hayır (default)** — simülatör fiyatıyla.

7. **Frontend gerçek veriyi mi gösteriyor?**  
   **Hayır** — simüle; banner ile itiraf ediyor.

8. **Production’da mock riski var mı?**  
   **Evet** — default config simulated.

---

## 17. NEXT STEP (max 5 — do not implement here)

1. Decide production invariant: **`DATA_PROVIDER=simulated` forbidden when `MODE`/deploy=prod** (or force `required` until live works).  
2. Add **`data_source_kind` (+ optionally run_id)** to predictions and trades before any live switch.  
3. Policy: **no STRONG_BUY/BUY unless `is_live_market`** in production profile (paper may keep sim).  
4. Isolate or freeze **companion** mock market to avoid dual truth.  
5. Only then: choose licensed feed and implement real provider **without** mock fallback.

---

*End of MOCK DATA FORENSIC AUDIT. No application code was modified.*
