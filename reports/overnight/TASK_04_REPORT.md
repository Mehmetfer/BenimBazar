TASK: 04 — My Listings / Moderation UX
STATUS: VERIFIED (API + widget) — browser click E2E flaky/NOT fully proven
FILES CHANGED:
- changex_app/lib/screens/my_listings_screen.dart
- changex_app/lib/utils/listing_status_ux.dart
- listing detail owner moderation panel / ribbons
- API listing visibility / photos[] / user_message enrichment
- changex/tests/test_my_listings_moderation_ux.py
ROOT CAUSE: Pending/rejected/deleted states unclear; pending listings invisible on home without owner UX.
FIX: Status chips/filters; İncelemede / Uygun bulunmadı ribbons; owner moderation panel vs offer CTA rules.
TESTS BEFORE: UX incomplete; Flutter suite failing historically
TESTS AFTER: moderation UX API tests + Flutter widget tests green
NEW TESTS: My listings chips; pending detail panel; status UX mapping tests
REGRESSION: changex/tests 252; flutter test 16
KNOWN LIMITATIONS: CanvasKit browser click E2E remained flaky — not claimed as browser-complete.
COMMIT: deda83b Clarify My Listings moderation UX for every listing state
