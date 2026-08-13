# TASK 18 — STRATEGY PERFORMANCE MEMORY

## Status: PASS

## Summary
StrategyMemoryRow metrics + PROPOSED_UPDATE only (auto_applied=False, human approval required).

## Artifacts
- borsa_bot/decision/feedback.py

## Tests
- test_g18_proposed_update_not_auto_applied

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
