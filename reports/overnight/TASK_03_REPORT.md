TASK: 03 — Listing Edit / Photo Management
STATUS: VERIFIED
FILES CHANGED:
- changex/app/media_storage.py (soft-delete in-tx; physical unlink after COMMIT)
- listing photo prune / orphan cleanup path
- changex/tests/test_listing_photo_edit.py
- Flutter edit_listing_screen.dart
ROOT CAUSE: Photo delete/edit risked orphans or unlink-before-commit inconsistency.
FIX: Soft-delete inside transaction; unlink only after successful COMMIT; edit API ownership checks; UI photo management chrome.
TESTS BEFORE: Edit/delete lifecycle incomplete
TESTS AFTER: test_listing_photo_edit.py green; image suites included in focused 116 pass batch
NEW TESTS: Edit lifecycle + refresh persistence cases
REGRESSION: changex/tests 252; flutter test 16
KNOWN LIMITATIONS: Orphan cleanup admin endpoint exists; historical disk orphans may remain on old DBs.
COMMIT: db2ee13 Add safe listing photo edit cleanup with rollback
