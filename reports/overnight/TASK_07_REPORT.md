TASK: 07 — Exchange Graph / Chain Engine Hardening
STATUS: VERIFIED (proposal engine) — settlement still NOT_IMPLEMENTED
FILES CHANGED:
- changex/app/matching/integrity.py
- changex/app/matching/settlement.py
- graph/engine/proposals/matchability/main.py updates
- changex/tests/test_chain_engine_hardening.py
- Flutter chain_engine_ux + listing notices
ROOT CAUSE: Proposal vs settlement blurred risk; stale edges; duplicate proposals; flag OFF UX unclear; Asset Lock stub not surfaced.
FIX: Integrity/dedupe/stale-edge revalidation; open-proposal reuse; explicit NOT_IMPLEMENTED settle endpoint; status/preferences user_message; UI honesty.
TESTS BEFORE: Graph 23 / Chain 35
TESTS AFTER: Graph 23 + Chain 35 preserved; hardening 17 passed
NEW TESTS: integrity, stale edge, settle 501, flag OFF messages, rematch dedupe
REGRESSION: changex/tests 252
KNOWN LIMITATIONS: CHANGE_CHAIN_ENABLED default false; Asset Lock / ownership transfer NOT_IMPLEMENTED (honest).
COMMIT: 8f7e1e8 Harden Exchange Graph and Chain Engine proposal/settlement boundary
