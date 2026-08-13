# AUTONOMY BASE REPORT

## Status: PASS (controlled / sandbox) — F8 NOT claimed

## Architecture

```
AUTONOMY CORE
├── Observer
├── Evidence Collector
├── Detector
├── Diagnoser
├── Planner
├── Proposal Engine
├── Sandbox Executor
├── Test Runner
├── Verification Engine
├── Rollback Manager
├── Learning Store
└── Audit Logger
```

Package: `autonomy/`  
State machine: `AutonomyState` with allow-listed transitions (no OBSERVING→DEPLOYED).  
Budgets: `AutonomyBudget` → `PAUSED_FOR_REVIEW` on limit.

## Loop

OBSERVE → DETECT → DIAGNOSE → PLAN → PROPOSE → SANDBOX → TEST → VERIFY  
→ PASS → READY_FOR_REVIEW  
→ FAIL → ROLLBACK → LEARN  

**No production mutate. No auto-deploy. No LIVE trading.**

## Failure injection (tested)

| Injection | Expected | Result |
|-----------|----------|--------|
| TEST_FAILURE | ROLLBACK + LEARN | PASS |
| BUILD_FAILURE | ROLLBACK | PASS |
| VERIFICATION_FAILURE | ROLLBACK | PASS |
| TIMEOUT | ABORT | PASS |
| RESOURCE_LIMIT | PAUSED_FOR_REVIEW | PASS |

## Tests
`autonomy/tests/test_autonomy_core.py` — 5 passed

## Coupling
- Reuses `self_verification/target` fixture
- Complements Night 2 `self_verification/f7_loop` + `borsa_bot/decision` F6 paper loop
