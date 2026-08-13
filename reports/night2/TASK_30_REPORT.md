# TASK 30 — F6/F7 FULL LOOP

## Status: PASS

## Summary
F6PaperLoop + F7ControlledLoop coupled safely; LIVE/self-deploy/F8 disabled.

## Artifacts
- borsa_bot/decision/pipeline.py, self_verification/f7_loop.py

## Tests
- test_g30_f6_f7_coupled_safely; suites: borsa+F7 123, CHANGE X 252, Flutter 16, companion 2

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
