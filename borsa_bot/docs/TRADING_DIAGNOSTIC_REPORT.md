# TRADING_DIAGNOSTIC_REPORT.md

## Question
**Why does Koca_Kafa keep losing on paper trades?**

## Answer (evidence-based)

1. `BIST_PAPER_AUTO_FOLLOW=true` was auto-trading on `DATA_PROVIDER=simulated` (random-walk).
2. Stops ~2% with fills that include commission+slippage → many sub-hour stop-outs.
3. `monitor_exits` closes **100%** at first stop/target — partial TP/trail not on follow path.
4. Heuristic EV with `MIN_EXPECTED_VALUE=0` did not subtract round-trip costs (now fixed to NET EV).
5. Docs already stated profitability unproven; autonomy ≠ edge.

## Measured (paper.db)

- Realized: -7334.09 TL | PF 0.395 | Exp -523.86/trade | WR 42.9%

## Loss share (of losing PnL)

- TIMING_ERROR: 45.8%
- STOP_ERROR: 32.5%
- OVERTRADING: 18.2%
- SIGNAL_ERROR: 3.4%

## Fixes applied this iteration

- Disable auto-follow by default (.env)
- Block auto-follow on SIMULATED/MOCK data even if flag true
- Store/compare NET EV after round-trip costs; NO_TRADE when net<=0
- Loss attribution API `/api/paper/diagnostics`
