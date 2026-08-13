# TASK 14 — RISK ENGINE

## Status: PASS

## Summary
Independent risk gate: max size/exposure/daily loss/drawdown/SL/TP/vol/liquidity/confidence/consecutive losses → APPROVED/REDUCED/REJECTED.

## Artifacts
- borsa_bot/decision/risk_gate.py

## Tests
- test_g14_*

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
