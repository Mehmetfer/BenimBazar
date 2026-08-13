TASK: 09 — Controlled Self-Verification
STATUS: VERIFIED (sandbox foundation) — not production autonomy
FILES CHANGED:
- self_verification/* (engine, sandbox, audit, probes, proposers, runner, target)
- self_verification/tests/test_controlled_loop.py
- scripts/self_verify.sh
- pytest.ini testpaths
ROOT CAUSE: F7 loop absent (phase audit FAILED).
FIX: OBSERVE→…→READY_FOR_REVIEW/ROLLBACK with audit JSONL; proposal-before-apply; sandbox-only mutations; self-deployment flag forbidden; failure-injection rollback tests.
TESTS BEFORE: F7 absent
TESTS AFTER: self_verification/tests 9 passed; full pytest 351
NEW TESTS: happy path READY_FOR_REVIEW; failure injection ROLLBACK; production mutate forbidden
REGRESSION: 351 full; changex 252; flutter 16
KNOWN LIMITATIONS: Target is self-verification fixture, not autonomous CHANGE X production rewrite; HUMAN APPROVAL required for deploy; F8 DISABLED.
COMMIT: 82bbf8e Add F7 controlled self-verification sandbox loop
