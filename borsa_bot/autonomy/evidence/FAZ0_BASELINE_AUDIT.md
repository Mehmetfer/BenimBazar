# FAZ 0 — Baseline Audit (Autonomy Protocol)

Generated during autonomy protocol work. LIVE broker remains locked.

## Modules present (on protocol base branch)

| Area | Location | Notes |
|------|----------|--------|
| Level 7 | `level7/` | Research/hypothesis/lab; human promote |
| Level 8 | `level8/` | Continuous learning; `full_level8_claimed=False` by design |
| Agents | `decision/agents/`, `decision/governor.py` | Propose-only |
| Orchestrator | `autonomous/engine.py`, `autonomous/agent.py` | Paper default |
| Providers | `data/providers.py`, `crypto/providers/` | BIST vs CRYPTO factories separated |
| Risk | `risk/`, `autonomous/gates.py` | Kill switch / fail-closed |
| Paper/shadow/live | `execution/`, settings | LIVE_BROKER_ENABLED default false |
| Config | `.env.example` | Documents CRYPTO_PROVIDER=auto + LIVE locks |
| API | `dashboard/app.py` | BIST + `/api/crypto/*` |

## Baseline pytest (before protocol fixes)

- Recorded: `autonomy/evidence/baseline_pytest.txt` (initial run under polluted `.env`)
- Result: **297 passed, 4 failed**
- Failures (root causes recorded as lessons):
  1. `CRYPTO_ENABLED=true` in local `.env` broke default-off tests
  2. Crypto detail raised on `BTC_TL` under OKX (no TR pairs)
  3. Governor `TRADING_HALT` vs test expecting `NORMAL`

## Post-fix pytest

- `autonomy/evidence/post_fix_pytest.txt`
- Result: **313 passed, 0 failed**

## Safety

- `LIVE_BROKER_ENABLED=false` asserted in acceptance tests
- No self-modifying production trading code in lesson store
