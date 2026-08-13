# Hardening Pass — Last ~20 Tasks Revisit

Self-owned quality pass over Night 2 F6/F7, overnight admin/autonomy, and messaging V1.

## Fixed (this pass)

| Area | Issue | Fix |
|------|--------|-----|
| Flutter chat | Contact WARN/BLOCK via string match | `ApiException.code` / `statusCode` + `isContactWarning` / `isContactBlocked` |
| Autonomy learning | Fail count never reset by PASS | `should_block` = consecutive FAILs since last PASS; PASS recorded to learning.jsonl |
| Messaging | Chat on PENDING listings | Only APPROVED/ACTIVE may start listing conversations |
| Messaging | Race on conversation create | IntegrityError → return existing row; partial unique index `idx_conv_listing_pair` |
| Messaging | Soft-delete missing | `DELETE /api/messages/{id}` + audit `MESSAGE_DELETED` |
| Messaging | Block nonexistent user | 404 |
| Messaging | Moderate missing report | 404; ACTIONED soft-deletes message body |
| Support | Contact policy BLOCK on tickets | Support never BLOCK/silent-rewrite; evidence note only |
| Support | Wrong audit on user reply | `SUPPORT_USER_REPLY` |
| Support | Attachment URL theft | `_assert_photo_urls_owned` on create/reply |
| Admin UI | Support/report actions thin | DESTEK transcript + ACTIONED/DISMISS; home unread badge |

## Regression (post-harden)

| Suite | Result |
|-------|--------|
| `pytest changex/tests` | **278 passed** (277 + attachment ownership) |
| `pytest autonomy/tests` | 7 passed |
| `pytest borsa_bot/tests self_verification/tests` | 123 passed |
| `pytest companion/tests` | 2 passed |
| `flutter analyze` | clean |
| `flutter test` | 18 passed |

## Honest limits (unchanged)

- F8 not claimed; LIVE trading forbidden; no production auto-deploy
- Messaging V1: no WebSocket/push yet
- Seeded superadmin credentials remain known debt

## Phase (honest)

F6 ~78 · F7 ~84 · F8 16 FAILED · Messaging V1 COMPLETE (hardened)
