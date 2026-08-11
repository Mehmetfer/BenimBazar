# TRADE_PLAN.md — AI Trade Plan Engine

**Rule:** Creating a trade plan does **not** send an order.  
**Rule:** No “kesin kazanır” language — model estimate only.  
**Rule:** LIVE automatic execution remains OFF by default.

## Flow

```
AI TRADE PLAN
    ↓
RISK ENGINE validation
    ↓
USER NOTIFICATION (push / sound / TTS / SMS / in-app)
    ↓
USER APPROVAL  →  paper/execution
```

## Contents of a plan

- Entry zone (optimal) + Breakout plan B
- Stop (ATR + support/structure) + reason
- Targets 1/2/3 with probability & expected return (historical hit rate = NULL if unknown)
- R/R, confidence, win probability, position size, max risk TL
- Time horizon + holding estimate
- VALID_UNTIL + invalidation rules
- Chase warning if price left the zone
- State: WATCH → … → CLOSED / INVALIDATED

## API

`GET /api/trade-plan/{SYMBOL}`
