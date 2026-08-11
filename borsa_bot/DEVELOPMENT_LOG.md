# DEVELOPMENT_LOG — BIST Professional Quant Trading Engine

## 2026-08-11 — Baseline analysis (pre-expansion)

### Existing strengths (kept)
- Modular Python layout under `borsa_bot/`
- PAPER default, LIVE blocked, manual approval, kill switch
- Indicators + MTF + regime + multi-score signals + EV + capital modes
- Risk Engine veto, ATR stops, partial TP / trailing hooks
- Paper broker + duplicate protection + SQLite ledger
- Dashboard with decision explanation
- Unit tests green (17) before this expansion

### Gaps vs institutional target architecture
| Layer | Status | Action |
|-------|--------|--------|
| Universe selection | Missing → done | `/universe` liquidity/spread/vol/history + pump-dump heuristic |
| Factor engine | Partial → done | `/factors` MOMENTUM/VALUE/QUALITY/GROWTH/VOLATILITY |
| Price action | Thin → done | `/technical/price_action.py` |
| CCI / Williams %R | Missing → done | indicators extended |
| Alpha ensemble | Partial → done | `/alpha` with regime_fit |
| Portfolio construction | Ledger only → done | sizing + correlation |
| Risk verdicts | Binary → done | APPROVE/REDUCE/WAIT/REJECT |
| Walk-forward | Stub → done | `/walk_forward` (does not unlock LIVE) |
| Monte Carlo | Missing → done | `/monte_carlo` |
| Top ops / daily report | Missing → done | API endpoints |
| Post-trade / drift | Missing → done | `/analytics` |
| Real BIST/KAP/depth | Simulated | Honest stubs remain |

### Design principles locked
1. Önce hayatta kal → sonra kâr → sonra kârı büyüt
2. Risk Engine > Alpha/Signal > AI
3. Negative EV → NO TRADE; positive EV still needs Risk approval
4. No look-ahead; no fabricated microstructure when data absent
5. LIVE stays OFF unless user explicitly enables
6. Do not delete working modules; extend and wire

---

## 2026-08-11 — Institutional layer expansion

### Why extend instead of rewrite
Existing paper/risk/EV/dashboard already matched capital-protection philosophy. Rewriting would destroy validated tests and duplicate work.

### Still deferred
- Real market data adapters
- Calendar-true multi-month factor windows (bar proxies in simulator)
- Calibrated expectancy from live trade DB
- Broker integration — LIVE remains OFF

### Test gate
`pytest borsa_bot/tests -q` → **22 passed**
