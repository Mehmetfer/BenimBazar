TASK: 01 — Flutter UI/Test Stabilization
STATUS: VERIFIED
FILES CHANGED:
- changex_app/test/widget_test.dart
- changex_app/lib/screens/splash_screen.dart
- changex_app/lib/utils/url_utils.dart (Uri.base.origin crash fix)
- related listing UI screens for testability
ROOT CAUSE: Flutter widget tests failed (splash brand assertion; Uri.base.origin crash on file:// test hosts; splash auto-skipping admin entry).
FIX: Stabilize splash timer/navigation for tests; safe origin helper; expand widget coverage for create/listings/moderation chrome.
TESTS BEFORE: Flutter 0 passed / 1 failed (phase audit 2026-08-12)
TESTS AFTER: flutter analyze clean; flutter test 16 passed
NEW TESTS: Widget coverage for splash, login yönetim entry, create photo UI, my listings chips, detail moderation panel, carousel, fixtures preview, chain UX honesty.
REGRESSION: pytest changex/tests 252 passed; flutter analyze + flutter test green.
KNOWN LIMITATIONS: Headless browser file-picker Select→Refresh still NOT VERIFIED.
COMMIT: 8d4d922 Stabilize Flutter UI tests; fix Uri.base.origin crash (+ follow-ups 0ff884a, 91a3f34)
