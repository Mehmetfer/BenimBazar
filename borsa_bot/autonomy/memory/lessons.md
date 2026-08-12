# Engineering Lessons (Software Autonomy)

Persistent lessons for the autonomous coding agent. Also mirrored as JSON under `autonomy/lessons/`.

## Rules

1. **Execution retry changes require idempotency regression tests.**
2. **Financial ambiguity (UNKNOWN_ORDER, POSITION_MISMATCH, …) → HALT, never RETRY.**
3. **Unvalidated alternate provider → NO_TRADE / HALT.**
4. **Never delete tests or weaken assertions to pass.**
5. **Never unlock LIVE broker or clear kill switch via SE agent.**
6. **SI/ASE snapshots must not be `.py` modules under mypy roots.**
7. **Boolean `and` with lists is not a bool — coerce with `bool(...)` for typed APIs.**

## Successful patterns

- Allowlisted heuristic coder for known goal classes (provider recovery policy + tests).
- Orchestrator hard limits: max_iterations / max_retries / max_runtime / max_tool_calls.
- Checkpoint → implement → test → repair → quality gate → accept|rollback.

## Known gaps

- No LLM generative coder for arbitrary goals (UNKNOWN → SAFE STOP).
- Parallel sub-agents not scheduled.
- Multi-hour soak NOT VERIFIED → SE score capped below 9.6/10.0.
