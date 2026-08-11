# PROJECT_AUDIT.md — PROJECT GENESIS 2100

**Audit date:** 2026-08-11  
**Scope:** Full repository with focus on `borsa_bot/` (active quant system)  
**Constraint honored:** No broker live-order code proposed or written in this step.  
**Core law:** CAPITAL MUST SURVIVE · NO DATA, NO TRADE · LIVE NEVER DEFAULT ON

---

## 0. Executive snapshot

| Item | Finding |
|------|---------|
| Primary active system | `borsa_bot/` (~5.9k LOC Python) |
| Python | **3.12.3** |
| Frameworks | FastAPI, Uvicorn, python-dotenv, pytest, SQLite |
| Data | **Simulated only** (`DATA_PROVIDER=simulated`) |
| Broker | **None** — `PaperBroker` only; LIVE hard-blocked |
| AI models | Heuristic/rule ensembles — **no trained ML weights, no LLM required** |
| Tests | **26 passed** (`borsa_bot/tests/test_core.py`) |
| Mode default | `MODE=PAPER`, `REQUIRE_MANUAL_APPROVAL=true`, `KILL_SWITCH=false` |

Legacy siblings (not the Genesis core): WinForms `Koca_Kafa`, early `companion/`, Flutter `borsa_app/`, static `test_page/`.

---

## 1. Mevcut sistem

### 1.1 Repository layout (relevant)

```
/workspace
  borsa_bot/          ← GENESIS target (modular Python quant)
  companion/          ← earlier FastAPI chat/Borsa experiments
  borsa_app/          ← Flutter scaffold
  test_page/          ← mobile HTML demos
  Koca_Kafa.*         ← original C# WinForms companion
```

### 1.2 `borsa_bot` architecture (as implemented)

```
UNIVERSE → DATA(sim) → INDICATORS/TECHNICAL/PA
        → FACTORS / FUNDAMENTAL(stub) / NEWS(null-honest)
        → MARKET REGIME → ALPHA / ENGINES(LONG|SWING|DAY)
        → MODE SELECTOR / META-ish ensemble
        → EV / PROBABILITY heuristics
        → PORTFOLIO (ledger, sleeves, corr, stress)
        → RISK (APPROVE|REDUCE|WAIT|REJECT)
        → PAPER EXECUTION (duplicate guard)
        → DASHBOARD + analytics APIs
```

### 1.3 Modules present

| Path | Role |
|------|------|
| `data/` | Protocol + `SimulatedProvider` (10 stocks + XU100) |
| `universe/` | Liquidity/spread/vol/history + pump-dump heuristic |
| `indicators/` | EMA/SMA/RSI/MACD/ADX/ATR/BB/Stoch/StochRSI/VWAP/OBV/MFI/CMF/ROC/CCI/Williams |
| `technical/` | MTF aggregation, sector RS, price action |
| `factors/` | Momentum/Value/Quality/Growth/Volatility 0–100 |
| `fundamental/` | Synthetic fundamentals dict (explicit stub) |
| `news/` | Classifier exists; **live headline = None** (honest unavailable) |
| `market_regime/` | STRONG_BULL…STRONG_BEAR + breadth proxy |
| `alpha/` | Multi-strategy votes + regime_fit |
| `engines/` | LONG_TERM / SWING / DAY_TRADING + mode_selector + orchestrator |
| `ai/` | quality/confidence, specialist ensemble, calibration monitor |
| `signals/` + `strategy/` | Scores, service scan, ranking |
| `profit/` | EV, capital modes, trailing/breakeven/partial TP, no widen |
| `portfolio/` | SQLite ledger, sleeves, construction, stress/VaR approx |
| `risk/` | Entry/exit gates, day limits, kill/LIVE block |
| `execution/` | PaperBroker + SafetyGate |
| `backtest/`, `walk_forward/`, `monte_carlo/` | Illustrative validation on simulated paths |
| `analytics/` | Reports, post-trade lessons, tops |
| `dashboard/` | FastAPI + mobile HTML |
| `config/` | Frozen Settings from `.env` |
| `database/paper.db` | Local SQLite paper state |
| `tests/test_core.py` | 26 unit/integration-style tests |

### 1.4 API surface (`dashboard/app.py`)

- `GET /api/health`
- `GET /api/dashboard`
- `POST /api/execute` (paper + optional `approved`)
- `POST /api/reset`
- `GET /api/backtest`
- `GET /api/opportunities`
- `GET /api/daily-report`
- `GET /api/walk-forward` (**`live_allowed: false`**)
- `GET /api/monte-carlo`
- `GET /api/multi-horizon`
- `GET /api/ai-daily-report`
- `GET /`

### 1.5 Configuration / secrets

- `.env.example` documents risk, sleeves, day limits — **no broker keys present** (correct for current stage)
- `.env` gitignored (verified via ignore rules intent)
- Dependencies: `fastapi`, `uvicorn`, `python-dotenv`, `pytest` only

### 1.6 Trading logic (truthful summary)

- Multi-score + factor blend + EV gate + Risk Engine veto
- Three horizon engines evaluated separately; capital sleeves configured
- Day trading pause limits exist
- Manual approval required before paper fill when enabled
- **No real fills, no real KAP, no order book, no trained neural nets**

---

## 2. Güçlü yönler

1. **Correct safety posture:** LIVE blocked in paper broker + risk preflight; manual approval default ON.
2. **Honest data gaps:** MTF marks `UNAVAILABLE` for lower TFs; news returns null when no feed; day ORB not faked as true session ORB.
3. **Risk-first design:** Negative EV reject, RR floors, no DCA default, stop never widens, kill switch, capital protection modes.
4. **Modular growth path:** Provider protocol ready for real adapters without rewriting signal/risk.
5. **Horizon separation started:** LONG / SWING / DAY + sleeves + mode selector.
6. **Explainability hooks:** reasons / risks / opportunity cards / daily briefing APIs.
7. **Test discipline present:** kill switch, duplicate orders, stale/spread safety, EV reject, engines separate — **26 green**.
8. **No hallucinated broker SDK** in codebase.

---

## 3. Kritik problemler

| ID | Problem | Severity |
|----|---------|----------|
| P1 | **All analytics are on simulated OHLCV** — any expectancy/WF/MC result is illustrative, not edge proof | CRITICAL |
| P2 | **Fundamentals are hard-coded fake numbers** — long-term engine can look “smart” without real bilanço | CRITICAL for LONG |
| P3 | **No real multi-timeframe feeds** — MTF is bar aggregation of one simulated series | HIGH |
| P4 | **Walk-forward is not true chronological WF** — independent seeded backtests approximate folds | HIGH |
| P5 | **Alpha “historical expectancy” is static placeholders** — not measured from OOS trades | HIGH |
| P6 | **Sleeve budgets not enforced in ledger** — config exists; paper fills still use shared cash pool | HIGH |
| P7 | **Single monolithic `TradingService.scan` + orchestrator overlap** — dual paths risk drift/duplication | MEDIUM |
| P8 | **Decision provenance incomplete** — no Decision ID / model version / data snapshot hash | MEDIUM |
| P9 | **Calibration/monitor not persisted** — restarts lose confidence haircut state | MEDIUM |
| P10 | **Docs lag Genesis target** — missing ARCHITECTURE/RISK_MODEL/LIVE_GATE etc. | MEDIUM |

---

## 4. Riskler (güvenlik / sermaye / operasyon)

### 4.1 Sermaye riskleri
- Simulated edge → **false confidence** if user treats dashboard as live alpha.
- Shared cash across sleeves → day losses can conceptually affect long capital until hard ledger splits exist.
- Heuristic P(win)/EV may be **miscalibrated**; overtrading if thresholds loosened without OOS.

### 4.2 Güvenlik
- Dashboard binds `0.0.0.0` — fine in cloud sandbox; **must not expose unauthenticated execute on public internet** without auth.
- No auth/JWT on `/api/execute` or `/api/reset`.
- Cloudflare quick tunnels historically used for mobile demo — treat as **demo only**.
- No broker secrets yet — good; when added need encrypted secret store, never log tokens.

### 4.3 Operasyonel
- Stale-data checks exist but depend on simulator tick freshness.
- No broker heartbeat / order-status reconciliation (N/A until broker).
- Chaos/failure suite incomplete (DB lock, partial write, clock skew beyond unit stubs).

### 4.4 Model / research risk
- Overfitting pressure as features accumulate on same simulated generator.
- Regime labels can flip too easily on short noise (mitigated partially, not proven).

---

## 5. Eksik modüller (vs Genesis 2100 target)

| Target package | Status |
|----------------|--------|
| `/data_quality` | Missing |
| `/data_provenance` | Missing |
| `/microstructure` | Missing (spread only on quote) |
| `/meta_ai` (first-class) | Partial (`ai/ensemble` + mode_selector) |
| `/red_team` adversarial | Missing |
| `/probability` formal engine | Partial (`profit/ev`) |
| `/research` lab + hypothesis reports | Missing |
| `/model_monitor` drift persistence | Partial (in-memory calibration) |
| `/docs` suite (ARCHITECTURE, RISK_MODEL, …) | Mostly missing (only DEVELOPMENT_LOG/README) |
| CRISIS regime | Missing (only 5 regimes) |
| Monthly TF / true 1M bars | Missing |
| SIZE factor | Missing |
| Feature correlation matrix automation | Missing |
| Strategy championship + retirement workflow | Ranking example only |
| NO_TRADE_ENGINE as standalone | Embedded heuristics only |
| Trade journal AI weekly patterns | Thin post_trade |
| Self-critique BULL/BEAR/NEUTRAL cards | Missing |
| Decision quality (good process vs lucky PnL) | Missing |
| Live trading PASS/FAIL gate criteria docs | Missing |
| Chaos/failure tests | Missing |
| Auth for dashboard APIs | Missing |
| Real BIST/KAP/broker adapters | Missing |

---

## 6. Mimari önerisi (2026-applicable Genesis)

Keep existing code. Evolve toward:

```
/data (+adapters) → /data_quality → /data_provenance
/universe → /factors → /technical → /fundamental → /news → /microstructure
/market_regime → /sector
/alpha/* → /engines/{long,swing,day}
/meta_ai (+ red_team) → /probability
/portfolio (sleeves enforced) → /risk (veto supreme)
/execution (paper now; broker later behind gates)
/backtest → /walk_forward → /monte_carlo → /model_monitor
/research (offline only)
/dashboard /docs /tests
```

**Non-negotiables**
1. Risk Engine > Meta AI > Alphas  
2. Missing data → NULL → often NO_TRADE  
3. Sleeve-isolated cash ledgers  
4. LIVE behind explicit multi-gate checklist  
5. Research strategies never auto-deploy  

**Market State (“digital twin” as representation only)**  
Index/sector/stock + vol/liquidity/momentum/breadth/news/macro/correlation snapshot object — never claim perfect twin.

---

## 7. Öncelik sırası (development order)

### Phase A — Harden foundation (before any new “AI brain” features)
1. Write remaining docs: ARCHITECTURE, RISK_MODEL, LIVE_TRADING_GATE, DATA_SOURCES, BACKTEST_PROTOCOL  
2. `data_quality` + `data_provenance` for every decision  
3. Enforce capital sleeves in ledger (separate cash buckets)  
4. Expand failure tests (stale, duplicate, kill, DB, clock)  
5. Dashboard auth or bind localhost-only for execute  

### Phase B — Real data adapters (still PAPER)
6. Choose BIST market-data vendor (delayed OK for research)  
7. KAP/news adapter with source_quality + unavailable path  
8. Replace fake fundamentals with FinTables/company filings API if licensed  
9. True calendar MTF stores (1D/1W), mark intraday gaps honestly  

### Phase C — Validation rigor
10. True walk-forward + OOS gates with PASS/FAIL thresholds  
11. Calibrate P(win) from paper journals; Brier/calibration curves  
12. Strategy championship + retirement states  
13. Red-team + self-critique cards on opportunity UI  

### Phase D — Paper → small live (only after gates)
14. Broker adapter behind feature flag  
15. Order-status machine + reconcile + kill on unknown  
16. Manual approval live  
17. Tiny capital live with daily loss circuit breakers  
18. Automated live **last**

**Do not start Phase D until Phase B+C pass.**

---

## 8. Gerekli veri kaynakları (eksik / gerekli)

| Data | Needed for | Current |
|------|------------|---------|
| BIST equities OHLCV (1m–1d) | Day/Swing/MTF | Simulated |
| BIST-100 + sector indices | Regime/breadth | Simulated XU100 only |
| Bid/ask/spread continuous | Microstructure/day filters | Synthetic spread on last bar |
| Depth / imbalance | Optional day alpha | **Absent → must be NULL** |
| KAP disclosures | News veto | **Absent (honest null)** |
| Fundamentals (IS/BS/CF) | Long-term | Fake stub table |
| Corporate actions / dividends | Long-term | Absent |
| Macro (rates, FX, CDS optional) | Regime context | Absent |
| Borrow/short availability | Future shorting | Out of scope (long-only MVP) |

---

## 9. Eksik broker / API bilgileri

**None configured — correctly.** To even prepare live later, user must supply (not now):

- Broker name (e.g. Matriks, AlgoLab, Interactive local intermediary, bank API)
- Environment URLs (paper vs live)
- API key / secret / certificate storage method
- Account id, sub-accounts for sleeves
- Order types supported (limit/market/IOC)
- Rate limits, session hours, lot size rules
- Order status webhook vs poll
- Fee schedule (commission, BSMV, exchange fees)

Until these exist: **no live order module.**

---

## 10. LIVE trading — missing controls (gate checklist)

Present today:
- `MODE=PAPER` default  
- PaperBroker rejects LIVE  
- Kill switch config  
- Manual approval flag  
- Daily/weekly/drawdown style gates (portfolio + day)  
- WF endpoint forces `live_allowed: false`  

Missing before LIVE can be considered:
- [ ] Documented PASS/FAIL criteria per stage (BACKTEST→OOS→WF→MC→PAPER→MANUAL→SMALL LIVE)  
- [ ] Minimum paper trading duration + trade count thresholds  
- [ ] Real-data OOS performance floors (Sharpe/DD/EV)  
- [ ] Broker connectivity health + order reconcile loop  
- [ ] Portfolio mismatch detection vs broker positions  
- [ ] Encrypted secrets + no-secret logging policy enforcement tests  
- [ ] AuthN/AuthZ on execute endpoints  
- [ ] Per-sleeve live risk caps  
- [ ] Explicit human “ENABLE_LIVE=true” + second confirmation  
- [ ] Rollback / flatten-all emergency procedure  
- [ ] Clock sync check vs exchange clock  
- [ ] Model version pinning + provenance replay  

**Verdict:** LIVE must remain **OFF**. System is a **paper market-intelligence scaffold**, not a production broker bot.

---

## 11. Test durumu (this audit)

```
PYTHONPATH=/workspace/borsa_bot pytest borsa_bot/tests -q
→ 26 passed
```

Coverage is good for core gates; weak for chaos, provenance, real adapters, sleeve isolation, auth.

---

## 12. Audit conclusion

`borsa_bot` is a **credible capital-preservation-oriented paper architecture** with the right philosophical defaults (NO TRADE, Risk veto, LIVE off, honest nulls).  

It is **not** yet a Genesis-complete autonomous wealth system: data is simulated, fundamentals/news are stubs, validation is illustrative, sleeves are not ledger-hard, and broker controls for LIVE are incomplete by design.

**Next allowed step after this audit:** implement Phase A documentation + data quality/provenance + sleeve enforcement + failure tests — still **without** live broker orders.
