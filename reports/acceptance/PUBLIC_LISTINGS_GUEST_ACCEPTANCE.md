# PUBLIC LISTINGS GUEST ACCEPTANCE

Guest-first public listings UX + backend gates.

## Results

| Check | Result |
|-------|--------|
| Guest Listings | PASS |
| Listing Detail | PASS |
| Search | PASS |
| Filtering | PASS |
| Trade Login Gate | PASS |
| Messaging Login Gate | PASS |
| Create Listing Login Gate | PASS |
| Deep Link | PASS |
| Private API Protection | PASS |
| RBAC Regression | PASS |
| Full Regression | PASS |

## Evidence

- Backend: `changex/tests/test_public_listings_guest.py`
- Flutter: splash → `HomeScreen(user: null)`; `AuthIntent` login gates with return route
- Python monorepo: **413** passed (`changex` 281 + autonomy/borsa/self_verification/companion 132)
- Flutter: analyze clean · **19** passed
- **Grand total: 432 passed, 0 failed**

## UX model

App Open → Public Listings (guest browse) → interact → Login/Register with reason → resume intended action.
