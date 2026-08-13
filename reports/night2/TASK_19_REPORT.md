# TASK 19 — CALIBRATION ENGINE

## Status: PASS

## Summary
CalibrationStatus CALIBRATED/OVERCONFIDENT/UNDERCONFIDENT/INSUFFICIENT_DATA; CalibrationMonitor.status() feeds strategy confidence dampen + F6 evidence.

## Artifacts
- borsa_bot/decision/feedback.py, ai/calibration.py, strategy/service.py

## Tests
- test_g19_calibration_status_overconfident

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
