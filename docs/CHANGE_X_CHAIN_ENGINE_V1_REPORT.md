# CHANGE X — CHANGE CHAIN ENGINE V1 REPORT

**Status:** CHANGE CHAIN PROPOSAL ENGINE READY  
**Not claimed:** CHANGE CHAIN SETTLEMENT IMPLEMENTED

## Scope

Multi-party barter cycle discovery and consent-only chain proposals:

- Graph: listing nodes + directed WANT→HAVE edges (on-demand, not fully materialized)
- Candidate pruning (moderation / inventory / opt-in / category / value / owner)
- Cycle detection (min length 3, max `CHANGE_CHAIN_MAX_LENGTH` default 4)
- Chain Proposal persistence + all-party consent
- **No money / TL / cash / monetary escrow**
- **No Asset Lock settlement / ownership transfer**

## Feature flag

- `CHANGE_CHAIN_ENABLED=false` (production default)
- Disabled → `POST /api/change-chain/match` → **501 `CHANGE_CHAIN_DISABLED`**
- Tests enable the flag explicitly via monkeypatch

## Graph architecture

| Concept | Implementation |
|--------|----------------|
| Node | Eligible listing (`APPROVED` + `AVAILABLE` + `chain_opt_in` + `CHAIN_ALLOWED` + active owner) |
| Edge | Structured WANT of source compatible with HAVE of target |
| Storage | Edges computed in-memory; only proposals persisted |
| Pruning | Category index + compatibility matrix `CHANGE_X_CATEGORY_COMPAT_V1` |

## Rules enforced

- Self-loop rejected
- 2-node cycles rejected (min length 3)
- Same owner at most once per chain
- Free-text `wanted_items` alone cannot open an edge
- Integer `mandal_units` value bands + gap tolerance
- Accept re-validates moderation + inventory (stale / EDIT_REQUIRED → 409)

## Proposal lifecycle (consent only)

`PROPOSED` → `PARTIALLY_ACCEPTED` → `ACCEPTED` | `REJECTED` | `EXPIRED` | `CANCELLED`  
Settlement stubs (`LOCKING`…`COMPLETED`) exist in enum only.  
`AssetLockProvider` → `NOT_IMPLEMENTED` (never called by consent path).

## APIs

- `POST /api/change-chain/match`
- `GET /api/change-chain/proposals`
- `GET /api/change-chain/proposals/{id}`
- `POST /api/change-chain/proposals/{id}/accept` (idempotent)
- `POST /api/change-chain/proposals/{id}/reject` (idempotent)

## Scoring / explainability

Reuses `ScoreProvider` / `ScoreBreakdown` components (`category/want/value/location/condition/preference`).  
Chain score = mean of edge totals + per-edge reasons.

## Performance

Benchmark script: `changex/tests/bench_chain_engine.py`  
Fixture sizes: 100 / 500 / 1_000 / 5_000 / 10_000 — reports p50/p95/p99, candidate/edge/cycle counts.  
No production RPS claims.

## Tests

Chain Engine suite: `changex/tests/test_chain_engine_v1.py` (≥35 cases covering gates, cycles, consent, idempotency, flag, AssetLock stub).  
Baseline suites remain green.

## Remaining risks

- O(n·k) edge generation still grows with category fan-out; further sharding needed at very large scale
- Asset Lock / atomic multi-party settlement not implemented (next stage)
- Proposal UX in Flutter feed is partial; listing ribbon UI is separate

## Verdict

**CHANGE CHAIN PROPOSAL ENGINE READY**
