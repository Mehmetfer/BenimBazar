TASK: 02 — Listing Photo Full Stack
STATUS: VERIFIED (API/full-stack) — browser Select NOT VERIFIED
FILES CHANGED:
- changex/app/main.py (upload endpoints)
- changex/app/media_storage.py / ownership registry
- changex/tests/test_listing_photo_fullstack.py
- changex/tests/fixtures/*
- changex_app create listing photo-first UI
ROOT CAUSE: Photo upload/ownership/validation gaps; weak frontend picker path historically.
FIX: Structural image validation; media_uploads ownership; create→upload→DB→listing relation API path; fixtures for real bytes.
TESTS BEFORE: Image path incomplete / prior e2e flaky
TESTS AFTER: test_listing_photo_fullstack + image e2e suites green (part of 252)
NEW TESTS: Fullstack scenarios 1–10; fixture-based validation cases
REGRESSION: changex/tests 252; flutter test 16
KNOWN LIMITATIONS: USER→native file dialog Select in real browser = NOT VERIFIED (do not substitute API for browser).
COMMIT: 78cce87 Complete listing photo full-stack ownership and validation (+ 081880b, f86e385)
