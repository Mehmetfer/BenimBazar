# Master Gap Analysis — Autonomous Coding Agent

- Generated: analysis-only phase (no implementation yet at time of writing)
- Baseline verified this run: **427 passed / 0 failed**
- G3 hard mypy: **PASS**
- Engineering autonomy (unchanged): **8.45/10**
- Prior SE autonomy claim: **9.4/10 PARTIALLY VERIFIED** (local ASE benches)
- Live-money: **NOT VERIFIED**
- full_level8_claimed: **FALSE**

## 1. Real repository layout (not assumed names)

| Requested | Reality |
|-----------|---------|
| `strategy/` | EXISTS |
| `execution/` | EXISTS |
| `risk/` | EXISTS |
| `portfolio/` | EXISTS |
| `providers/` | NO top-level → `data/providers.py`, `crypto/providers/` |
| `market_data/` | NO top-level → `data/`, `market_regime/` |
| `configuration/` | → `config/` |
| `persistence/` | → `database/`, `portfolio/ledger.py` |
| `logging/` | → `logs/`, structured audit modules |

Autonomy stack present: `autonomy/`, `agentic_se/`, `self_improvement/`, `decision/ade/`, `trading_safety/`, `autonomous/`, `level7/`, `level8/`.

## 2. Baseline

| Check | Result |
|-------|--------|
| pytest `tests/` | **427 passed / 0 failed** |
| Historical noted baseline | 339 (pre trading-safety/ADE/SI/ASE) — evolved, not reset |
| G3 hard mypy | **PASS** (31 scoped files) |
| Engineering score | **8.45 unchanged** (not re-inflated) |

## 3. Capability audit

| Capability | Status | Notes |
|------------|--------|-------|
| Repository understanding | EXISTS | `agentic_se/discovery.py` |
| Code search | PARTIAL | regex `find_files`, no semantic index |
| Task decomposition | PARTIAL | heuristic `decompose.py` |
| Planning | PARTIAL | TaskPlan + stages |
| File editing | PARTIAL | full-file writes only |
| Code generation | PARTIAL | needs external `WriteFn` / SI templates — **no NL→code** |
| Test generation | PARTIAL | via callbacks/templates |
| Test execution | EXISTS | `self_improvement/verify.py` |
| Failure analysis | PARTIAL | `autonomy/failure.py` + repair |
| Root-cause analysis | PARTIAL | string hypotheses |
| Self-repair | PARTIAL | often restore/refuse without codegen |
| Regression detection | EXISTS | baseline_guard + verify |
| Git awareness | PARTIAL | inspect only |
| Rollback | EXISTS | CheckpointStore + SI sandbox |
| Memory | PARTIAL | memory JSON; resume not wired |
| Lessons | EXISTS | `autonomy/lessons/` |
| Research | PARTIAL | L7 trading research; no SE web research |
| Tool orchestration | PARTIAL | hardcoded pipelines |
| Long-running tasks | PARTIAL | stages exist; soak NOT VERIFIED |
| Checkpointing | EXISTS | |
| Self-review | PARTIAL | checklist review |
| Security review | PARTIAL | often hardcoded True |
| Performance review | MISSING | |
| Self-improvement | PARTIAL | SI-1..7; SI-8/9 fail |
| **Central Orchestrator** | **MISSING** | highest-value gap |
| Parallel subtasks | MISSING | |
| Benchmark suite | EXISTS | ASE 9/9 |
| SE safety gate | EXISTS | allowlist/denylist |
| Trading invariant protection | EXISTS | frozen fields + denylist |

## 4. Target architecture (minimal overlay)

```
USER TASK → ORCHESTRATOR (new thin layer)
              ├── PLANNER (decompose)
              ├── RESEARCHER (discovery + find_files + optional L7)
              ├── CODER (heuristic/template → allowlisted writes)
              ├── TESTER (pytest/mypy)
              ├── DEBUGGER (repair_loop + bounded retries)
              ├── REVIEWER (review + quality)
              └── SAFETY GATE → ACCEPT | ROLLBACK → MEMORY → NEXT
```

Reuse: `agentic_se/*`, `self_improvement/verify`, `autonomy/lessons`, `autonomy/failure`.  
Do not rewrite trading `engines/orchestrator.py`.

## 5. Implementation roadmap (post-analysis)

1. Central Orchestrator with hard limits
2. Heuristic Coder (no required WriteFn for known goal classes)
3. Wire TaskContext resume
4. Honest security gate check
5. Autonomous demo task: provider recovery policy + regression tests (allowlisted)
6. Benchmark + report update (no score inflation beyond evidence)

## 6. Risks

- Expanding write allowlist into `risk/` / `trading_safety/` / broker = forbidden
- Claiming Cursor-level without generative codegen + long soak = dishonest
- Provider recovery product code lives in `autonomous/recovery.py` — SE may enhance via **tests + policy modules under allowlist**, not by loosening HALT rules

## 7. Analysis verdict

**PARTIAL foundation exists.** Missing critical path: **Orchestrator + callback-free coding** for USER TASK E2E.  
Proceed to implementation of items 1–5 above with implement→test→regression→verify cycles.
