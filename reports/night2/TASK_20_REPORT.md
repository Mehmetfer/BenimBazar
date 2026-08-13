# TASK 20 — DECISION REPLAY ENGINE

## Status: PASS

## Summary
DecisionReplayStore persists market/regime/signals/risk/decision/execution/result; replay() answers why.

## Artifacts
- borsa_bot/decision/replay.py

## Tests
- test_g20_replay_explains_decision

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
