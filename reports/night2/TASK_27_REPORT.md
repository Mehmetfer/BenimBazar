# TASK 27 — AUTOMATIC ROLLBACK

## Status: PASS

## Summary
Failure injection → ROLLBACK → restore baseline; production untouched.

## Artifacts
- self_verification/engine.py, f7_loop.py

## Tests
- test_g30_f7_full_loop_happy_and_rollback

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
