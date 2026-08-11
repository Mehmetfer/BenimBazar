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

## 2026-08-11 — Triple-horizon engines (LONG / SWING / DAY)

### Pre-change gate
- Architecture already has factors/alpha/risk/EV/paper
- Gaps: separate horizons mixed; no capital sleeves; no day-trade daily limits; no mode selector; thin specialist AI ensemble; no VaR/stress; no confidence calibration
- Risks: mixing horizons → wrong stops/holding; day losses eating long capital; overfit if engines share params uncontrolled
- Tests before change: **22 passed**

### Design decisions
1. Three engines stay **separate modules** — shared indicators/data, separate scores/decisions/capital
2. AI Mode Selector prioritizes engines from regime × volatility × trend; can return NO_TRADE
3. Capital sleeves in config: LONG_TERM / SWING / DAY / CASH_RESERVE — one sleeve cannot silently drain another
4. Day trading has hard daily pause limits
5. LIVE remains OFF
6. Scan aggressively, filter aggressively, trade selectively

### Why extend instead of rewrite
Existing paper/risk/EV/dashboard already matched capital-protection philosophy. Rewriting would destroy validated tests and duplicate work.

### Still deferred
- Real market data adapters
- Calendar-true multi-month factor windows (bar proxies in simulator)
- Calibrated expectancy from live trade DB
- Broker integration — LIVE remains OFF

### Test gate
`pytest borsa_bot/tests -q` → **22 passed**

---

## 2026-08-11 — Multi-channel Alert & Notification Engine (§61–80)

### Architecture
```
TRADING EVENT → EVENT BUS → ALERT MANAGER → PRIORITY → CHANNEL ROUTER
  → IN_APP / PUSH / SOUND / TTS / SMS → DELIVERY LOG
```

### Rules locked
- Notifications **never** change trading decisions
- **SIGNAL ≠ EXECUTION** (BUY_SIGNAL vs ORDER_FILLED separate)
- Channel failures never halt paper/risk/execution
- SMS/Push use provider stubs; no fabricated delivery without credentials
- Secrets scrubbed from notification logs
- Quiet hours bypass for STOP / KILL / RISK / ORDER_REJECTED
- Cooldown + event_id dedupe across channels

### Modules
- `alerts/` — events, bus, manager, bridge, messages, log, settings, channels
- Dashboard: `/api/notifications*`, inbox UI, sound/TTS client, settings toggles
- `monitor_exits()` emits STOP_LOSS / TAKE_PROFIT only after paper fill

### Test gate
`pytest borsa_bot/tests -q` → **36 passed**

