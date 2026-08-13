# Overnight Baseline — START

Captured before overnight admin/autonomy changes.

## Git

- Branch: `cursor/overnight-admin-autonomy-a857` (from `cursor/night2-f6-f7-a857`)
- Tip at baseline start: includes Night 2 F6/F7 commit `a1379c0`

## Test results

| Suite | Result | Notes |
|-------|--------|-------|
| `pytest changex/tests -q` | **252 passed** | Full CHANGE X |
| `pytest changex/tests/test_listing_image_e2e.py -q` | **7 passed** | Image E2E |
| `pytest changex/tests/test_exchange_graph_v1.py -q` | **23 passed** | Exchange Graph |
| `pytest changex/tests/test_chain_engine_v1.py -q` | **35 passed** | Chain Engine |
| `pytest changex/tests/test_trust_safety_v1.py -q` | **23 passed** | Trust & Safety |
| `flutter analyze` | **No issues found** | changex_app |
| `flutter test` | **16 passed** | Widget suite |

## Expected vs observed

| Claimed prior | Observed |
|---------------|----------|
| 189 CHANGE X tests | **252** (suite grew; do not regress below) |
| 7 image E2E | **7** |
| 23 Graph | **23** |
| 35 Chain | **35** |
| 23 Trust | **23** |

## Admin panel inventory (pre-change)

| Feature | Status |
|---------|--------|
| Admin Login | EXISTS |
| Dashboard KPIs | PARTIAL (pending count only) |
| Users | PARTIAL |
| Moderation queue | EXISTS |
| Photos moderation UI | PARTIAL |
| Reports | MISSING |
| Audit UI | MISSING (API per-listing audit EXISTS) |
| Health UI | MISSING (API `/api/health` EXISTS) |
| Stats API | EXISTS (`/api/admin/stats`) |
| Roles | EXISTS (superadmin assign) |

## Security debt (known, do not claim fixed by silence)

- Seeded superadmin `superadmin` / `14531453` (password resync on init)

## Hard limits for overnight

- No LIVE trading
- No production auto-deploy
- No test delete/skip/relax
- No fake listings/approvals/audit/images
- No authorization bypass

## Starting phase / score (from Night 2 re-audit)

- REAL PHASE: F6 paper + F7 sandbox
- F6: 78 · F7: 82 · F8: 16 FAILED
