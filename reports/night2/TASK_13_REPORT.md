# TASK 13 — SIGNAL FUSION

## Status: PASS

## Summary
AtomicSignal(score,confidence,source,timestamp) → CompositeSignal; conflicts + BUY+low liquidity → NO_TRADE.

## Artifacts
- borsa_bot/decision/signals.py

## Tests
- test_g13_*

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
