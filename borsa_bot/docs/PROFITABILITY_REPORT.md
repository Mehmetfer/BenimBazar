# PROFITABILITY_REPORT.md

## Status

**PROFITABILITY_STATUS:** `PROFITABILITY_UNPROVEN`

**AUTONOMY SCORE ≠ PROFITABILITY** — autonomy may be high while edge is unproven.


## Evidence (paper.db — VERIFIED)

- Closed rounds: **14**
- Win rate: **42.9%** (6W / 8L)
- Realized PnL: **-7334.09 TL**
- Profit factor: **0.395**
- Expectancy: **-523.86 TL / trade**
- Avg win / avg loss: **796.82 / -1514.38**
- Round-trip cost assumption: **0.5%** (commission+slippage both sides)


## Category PnL

- `TIMING_ERROR`: -5550.87 TL (45.8% of losses)
- `STOP_ERROR`: -3943.17 TL (32.5% of losses)
- `OVERTRADING`: -2205.46 TL (18.2% of losses)
- `SIGNAL_ERROR`: -415.51 TL (3.4% of losses)
- `EXECUTION_ERROR`: 0.0 TL
- `COST_ERROR`: 0.0 TL
- `DATA_ERROR`: 0.0 TL
- `TAKE_PROFIT_ERROR`: 163.73 TL
- `OTHER`: 4617.19 TL

## Root cause summary

Closed rounds=14 realized=-7334.09 TL PF=0.39 expectancy=-523.86/trade. Top loss sources: TIMING_ERROR -5551 TL (46%), STOP_ERROR -3943 TL (32%), OVERTRADING -2205 TL (18%), SIGNAL_ERROR -416 TL (3%). Auto-follow on simulated data + short-hold stop-outs are primary suspects when DATA_PROVIDER=simulated.


## Unverified

- Walk-forward OOS profitability: UNVERIFIED
- Sharpe / Sortino / Calmar on this book: UNVERIFIED (not computed here)
- Live money PnL: N/A (broker locked)
