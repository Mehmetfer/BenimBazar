# TEN LISTINGS VERIFICATION

Fixture note: exercised via FastAPI `TestClient` against real app routes,
temporary sqlite DB, and real PNG upload bytes (`fixtures/overnight_1x1.png`).
Not mocked listing/approval responses.

| # | Listing | Photo | Pending | Superadmin Approved | Audit Log | Public | Refresh | Result |
|---|---------|-------|---------|---------------------|-----------|--------|---------|--------|
| 1 | 1: Overnight Listing 01 — Elektronik Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 2 | 2: Overnight Listing 02 — Kitap Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 3 | 3: Overnight Listing 03 — Ev Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 4 | 4: Overnight Listing 04 — Spor Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 5 | 5: Overnight Listing 05 — Müzik Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 6 | 6: Overnight Listing 06 — Oyuncak Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 7 | 7: Overnight Listing 07 — Giyim Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 8 | 8: Overnight Listing 08 — Bahçe Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 9 | 9: Overnight Listing 09 — Sanat Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 10 | 10: Overnight Listing 10 — Diğer Unique | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

**Score: 10/10**

TEN LISTINGS VERIFIED

Superadmin actor_id used for approvals: 1

## Auth matrix (same run)
- Normal user approve/reject → **403**
- Unauthenticated decision → **401/403**

