TASK: 06 — CI/CD
STATUS: VERIFIED
FILES CHANGED:
- .github/workflows/ci.yml
- requirements.lock.txt
- pytest.ini (pythonpath=. borsa_bot)
- scripts/install.sh
- README.md (CI badge + CI Gate note)
ROOT CAUSE: No CI; plain pytest collection failed on borsa_bot without PYTHONPATH; non-deterministic deps.
FIX: GitHub Actions jobs (CHANGE X pytest, security, image E2E, API E2E, Flutter analyze/test, collection, CI Gate); lockfiles; root pytest.ini.
TESTS BEFORE: No CI; borsa collection errors without PYTHONPATH
TESTS AFTER: CI Gate success on PR; local full pytest 351 passed
NEW TESTS: N/A (pipeline); collection includes borsa without ad-hoc env
REGRESSION: CI run success (e.g. 31660474123 / 31660717886)
KNOWN LIMITATIONS: Branch protection requiring CI Gate must be enabled in GitHub settings by humans (API 403 for this agent).
COMMIT: e87a871 Add GitHub Actions CI with deterministic deps and pytest path fix
