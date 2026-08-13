# TASK 11 — MARKET OBSERVATION ENGINE

## Status: PASS

## Summary
MarketState nested Price/Volume/Volatility/Trend/Momentum/Liquidity/Regime/Portfolio with FieldValue.UNKNOWN (never silent 0).

## Artifacts
- borsa_bot/decision/market_state.py, observe.py

## Tests
- test_g11_unknown_not_silent_zero, test_g11_known_market_state_fields

## Security
- LIVE trading: **OFF**
- Production self-modification: **OFF**
- Human approval required for production patches

## Evidence notes
Night 2 implementation under `cursor/night2-f6-f7-a857`.
