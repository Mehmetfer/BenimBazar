# MESSAGING SYSTEM REPORT — GÖREV 36

## Starting State
- Messaging / support / peer block / message report: **MISSING**
- Baseline CHANGE X tests before this branch work: **264 passed**
- Overnight admin + 10 listings already on parent branch

## Implemented Features

### User → Support
- `POST /api/support/tickets` → `SUPPORT-######`
- Statuses: OPEN / IN_PROGRESS / WAITING_FOR_USER / RESOLVED / CLOSED
- Flutter: **Destek / Bize Ulaşın** (`SupportScreen`)

### Support → User (Admin)
- Admin Destek Merkezi tab + reply/resolve APIs
- User sees staff replies on ticket detail

### User → User (phone-free)
- Listing-linked conversations (`listing_id`, buyer, seller)
- Flutter: Mesajlar inbox + Chat detail + **Satıcıya Mesaj Gönder**
- Message status: SENT → DELIVERED → READ

### Security
- Participant-only access (IDOR → 403) — tested
- Unauthenticated → 401/403 — tested
- Block user prevents send — tested
- Contact detector (phone/email/social) with confidence; policy WARN/BLOCK/ALLOW; **no silent rewrite** — tested
- Configurable rate limits — tested (429)

### Moderation & Audit
- Message reports + admin list/action
- Audit actions without full message body: CONVERSATION_CREATED, MESSAGE_SENT, MESSAGE_REPORTED, USER_BLOCKED/UNBLOCKED, MESSAGE_MODERATED, SUPPORT_* 

### Admin dashboard
- Messaging KPIs: open support, reported messages, active conversations, blocked users

### Autonomy
- `autonomy/messaging_observe.py` maps delivery/API/moderation backlog → Observations (sandbox loop only)

## Security Tests
`changex/tests/test_messaging_system.py`: IDOR, block, contact warn, rate limit, report/moderation — **PASS**

## E2E Tests
- Buyer→seller→reply→refresh persistence — **PASS**
- Support roundtrip — **PASS**
- 3 listing message flows — **PASS** → `reports/overnight/MESSAGING_E2E_REPORT.md`

## Flutter Tests
- analyze: **No issues**
- test: **18 passed** (includes message seller CTA)

## 10 Listing Integration
- 3/3 messaging flows on approved listings (API E2E). Full 10 listing photo pipeline remains in overnight report; messaging integrated on sample of 3 as required.

## Admin Integration
- DESTEK tab + ÖZET messaging tiles — implemented

## Known Limitations
- No WebSocket/SSE live push yet (poll/refresh; schema ready for realtime later)
- No mobile push notification provider wired
- Admin does **not** get unbounded private transcript browser (reports + support only)
- Support attachments must be owned `/uploads/` URLs (theft blocked); rich ticket upload UX still minimal
- Peer “Reports” product for listings still separate from message reports

## Hardening (post-V1)
See `reports/overnight/HARDENING_PASS_REPORT.md`:
- APPROVED/ACTIVE-only listing chats; soft-delete; report ACTIONED soft-delete
- Support never BLOCK contact policy; attachment ownership
- ApiException structured contact codes; learning consecutive-fail reset
- Admin DESTEK transcript + unread badge

## Remaining Work
- Optional WebSocket layer
- Push notifications
- Soft-delete retention job (columns ready: `deleted_at`)
- Browser E2E for chat UI (widget + API proven; native browser not claimed)

## Acceptance checklist

| Item | Status |
|------|--------|
| User → Support | PASS |
| Support → User | PASS |
| User → User | PASS |
| Listing-linked conversation | PASS |
| Phone-free communication | PASS |
| Authorization | PASS |
| IDOR protection | PASS |
| Rate limiting | PASS |
| Block | PASS |
| Report | PASS |
| Moderation | PASS (report queue; ACTIONED soft-deletes) |
| Soft-delete own message | PASS |
| Support attachment ownership | PASS |
| Audit | PASS |
| Flutter UI | PASS |
| E2E | PASS |
| Refresh persistence | PASS |
| Regression green | PASS (278 changex target) |

**MESSAGING SYSTEM: COMPLETE** (V1 hardened — limitations above, no fake claims)

## Regression
- `pytest changex/tests -q` → **278** (messaging harden + attachment ownership)
- `flutter analyze` clean · `flutter test` 18

## CURRENT REAL PHASE
Professional admin + verified listings + F6/F7 + **messaging V1 hardened**

## CURRENT SCORE
~79/100 (F8 still disabled)

## NEXT IMPROVEMENT
WebSocket delivery + push unread; soft-delete retention policy tests

## AUTONOMY STATUS
Controlled — messaging health observations available; no production self-mutate
