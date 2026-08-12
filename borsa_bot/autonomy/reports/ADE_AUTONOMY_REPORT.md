# Autonomous Decision Engine Report

- Generated: `2026-08-12T06:01:05.491728+00:00`
- Engineering autonomy (prior): **8.45/10**
- Decision autonomy: **8.5/10**
- Trading safety (prior): **10.0/10**
- Live-money autonomy: **NOT VERIFIED**
- full_level8_claimed: **False**
- Verdict: **8.5 AUTONOMOUS DECISION ENGINE VERIFIED (paper/shadow); LIVE-MONEY AUTONOMY NOT VERIFIED**

## Suite results

- ADE unit: `PASS`
- Humanless E2E: `PASS`
- Trading safety regression: `PASS`

## Criteria

| Criterion | Status | Weight | Score |
|-----------|--------|--------|------:|
| Decision states (BUY..NO_TRADE) | PASS | 10% | 10.0 |
| Decision chain completeness | PASS | 12% | 10.0 |
| NO_TRADE as first-class | PASS | 10% | 10.0 |
| Position sizing hard cap | PASS | 10% | 10.0 |
| Immutable safety limits | PASS | 10% | 10.0 |
| Adaptive no safety bypass | PASS | 8% | 10.0 |
| Self-correction protocol | PASS | 8% | 10.0 |
| Decision+risk validators | PASS | 10% | 10.0 |
| Confidence gate (not authority) | PASS | 7% | 10.0 |
| Humanless E2E acceptance | PASS | 10% | 10.0 |
| Failure acceptance matrix | PASS | 5% | 10.0 |

## Roadmap

- 8.45 engineering (coding/validation) — prior
- 8.5 Autonomous Decision Engine — this scorecard
- 8.7 Autonomous Execution + Recovery — longer recovery matrix
- 8.9 Long-duration Humanless Validation — multi-session soak
- 9.0+ Production Trading Autonomy — requires LIVE-MONEY acceptance (separate)

## Notes

- Criterion raw weighted average=10.0/10 (quality of ADE suite); claimed autonomy level=8.5.
- Scores from evidence only; not inflated past the proven roadmap milestone.
- Learning cannot mutate risk limits / kill switch / fail-closed / auth.
- LIVE-MONEY AUTONOMY = VERIFIED is forbidden until dedicated live acceptance.

## Meaning

8.5 means the bot can independently observe, decide (including NO_TRADE),
size within immutable hard caps, validate, and execute **paper/shadow** orders
without human approval — while refusing to trade when safety cannot be established.
It does **not** mean LIVE-MONEY AUTONOMY = VERIFIED.
