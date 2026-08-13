# TASK 12 — MARKET REGIME ENGINE

## Status: PASS

## Summary
TradingRegime TREND_UP/DOWN/RANGE/HIGH_VOLATILITY/LOW_LIQUIDITY/UNKNOWN with confidence+evidence+features; consumed by fuse_signals + decide_from_state (not dead).

## Artifacts
- borsa_bot/decision/regime.py, signals.py, engine.py

## Tests
- test_g12_*, test_g13_fusion_uses_regime_not_dead

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
