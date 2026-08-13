# TASK 17 — PAPER TRADING FEEDBACK LOOP

## Status: PASS

## Summary
Result→P&L→lessons→next_decision_context (calibration_hint, size_multiplier, consecutive_losses). Not string-only.

## Artifacts
- borsa_bot/decision/feedback.py, pipeline.py

## Tests
- test_g17_lessons_affect_next_context

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
