# TASK 15 — DECISION ENGINE

## Status: PASS

## Summary
MARKET→FEATURES→REGIME→SIGNALS→CONFIDENCE→RISK→SIZE→DECISION→PAPER; standardized DecisionOutput; LIVE forbidden.

## Artifacts
- borsa_bot/decision/engine.py, pipeline.py; StrategyService.f6_paper_decide

## Tests
- test_g15_decision_output_schema

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
