TASK: 05 — API Security Hardening
STATUS: VERIFIED
FILES CHANGED:
- changex/app/main.py (CORS, 500 handler, logout, upload sniff, cancel/transition authz)
- changex/app/db.py (PBKDF2 + legacy rehash)
- changex/app/moderation/service.py (session revoke on suspend)
- changex/tests/test_api_security_hardening.py
- changex/tests/test_trust_safety_v1.py (suspend/login assertions)
ROOT CAUSE: IDOR/cancel gaps; client MIME trust; weak password hash; error/rate-limit leakage; CORS credentials with *.
FIX: Owner/staff cancel; staff-only generic trade transition; sniff-only extension; PBKDF2; suspend session wipe; logout revoke; generic 500; CORS credentials off with *.
TESTS BEFORE: Trust suite present; dedicated security matrix absent
TESTS AFTER: test_api_security_hardening.py 18 passed; changex/tests 252
NEW TESTS: owner/non-owner/admin/unauth matrices for read/update/delete/upload/photo-delete
REGRESSION: 252 changex; trust suite still 23
KNOWN LIMITATIONS: Default superadmin password force-resync remains known debt for legacy admin tests.
COMMIT: dbad579 Harden CHANGE X API authz, uploads, and session security
