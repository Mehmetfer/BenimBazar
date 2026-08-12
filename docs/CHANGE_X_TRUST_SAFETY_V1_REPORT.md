# CHANGE X TRUST & SAFETY V1 REPORT

AI Ön Moderasyon + Superadmin Nihai Yayın Onayı

**Nihai kural:** AI yayın kararının sahibi değildir. Superadmin nihai yayın otoritesidir.

```
UNAPPROVED = PUBLIC DEĞİL
UNAPPROVED = OFFER YOK
UNAPPROVED = TRADE YOK
UNAPPROVED = CHANGE CHAIN YOK
AI FAIL = YAYIN YOK
CRITICAL EDIT = YENİDEN MODERASYON
```

Change Chain algorithm **implement edilmedi** — yalnızca APPROVED gate stub’ı hazır.

---

## Test sonuçları

| Suite | Sonuç |
|-------|--------|
| Baseline (Core V1 + V1.1) | **94 passed** (korundu) |
| Trust & Safety V1 | **22 passed** |
| **TOPLAM** | **116 passed / 0 failed** |

Komut: `PYTHONPATH=/workspace pytest changex/tests -q`

---

## Moderation pipeline

```
USER CREATE
  → PENDING_MODERATION
  → AI PRE-MODERATION (ModerationProvider)
  → ADMIN_REVIEW | MODERATION_UNAVAILABLE | REJECTED(CHILD_SAFETY/trafficking)
  → SUPERADMIN QUEUE
  → APPROVED | REJECTED | EDIT_REQUIRED | ESCALATED | SUSPENDED
```

AI `SAFE` olsa bile otomatik APPROVED **yok**.

---

## Yeni / entegre listing state’leri

`DRAFT`, `PENDING_MODERATION`, `AI_REVIEW`, `ADMIN_REVIEW`, `MODERATION_UNAVAILABLE`, `APPROVED`, `REJECTED`, `EDIT_REQUIRED`, `ESCALATED`, `SUSPENDED`, legacy `ACTIVE`(=APPROVED), `RESERVED`, `TRADED`, `CANCELLED`, `EXPIRED`

Geçersiz transition’lar test edildi (`InvalidTransition`).

---

## Database değişiklikleri

- `trade_listings`: moderation_version, ai_*, risk_level, priority, approved_at/by, reason…
- `listing_photos` (per-url moderation_status + revision)
- `moderation_reviews` / `moderation_decisions`
- `users.user_risk_score`, `users.suspended`
- Migration: pre-existing `ACTIVE` → `APPROVED`

---

## API değişiklikleri

| Endpoint | Davranış |
|----------|----------|
| `POST /api/listings` | PENDING + AI; `user_message` |
| `GET /api/listings` | yalnızca APPROVED (+ cache + hard filter) |
| `GET /api/listings/mine` | sahibi tüm durumlar |
| `GET /api/listings/{id}` | onaysız gizli (owner/staff hariç) |
| `PATCH /api/listings/{id}` | status immutable; kritik alan → remotion |
| `POST /api/trades/offer` | `LISTING_NOT_APPROVED` (409) |
| `POST /api/change-chain/match` | stub + unapproved reject |
| `GET /api/admin/moderation/queue` | SUPERADMIN, risk priority |
| `POST .../decision` | APPROVE/REJECT/REQUEST_EDIT/ESCALATE/SUSPEND_USER |
| `GET .../audit` | decisions + audit_logs |

---

## AI abstraction

`ModerationProvider`:

- `analyze_text()`
- `analyze_image()`
- `analyze_listing()`

Payload: `status`, `risk_level`, `categories`, `confidence`, `policy_version`, `provider`, `model`, `timestamp`

Providers: Heuristic / Unavailable / Timeout / Malformed  
`validate_assessment()` → malformed confidence → UNAVAILABLE (no publication)

Kategoriler (örnek): SAFE, SEXUAL_CONTENT, NUDITY, CHILD_SAFETY, HUMAN_TRAFFICKING, DRUGS, WEAPON, ILLEGAL_GOODS, FRAUD, STOLEN_GOODS, VIOLENCE, HATE, PERSONAL_DATA, DANGEROUS_GOODS, …

**Testlerde gerçek zararlı görsel/PII yok** — sentetik keyword/stub.

---

## Image moderation

PHOTO URL → validation → AI image analyze → listing_photos satırı → Superadmin  
Yeni foto / kritik edit → `moderation_version++` → public foto gösterimi yok

---

## Revision sistemi

`moderation_version` her kritik edit’te artar; `approved_at/by` temizlenir.  
Eski APPROVE yeni revision üzerinde geçerli değil.  
Concurrent Superadmin: optimistic `version` → CONFLICT.

---

## RBAC

| Rol | APPROVE |
|-----|---------|
| user | hayır (STATUS_IMMUTABLE) |
| admin | hayır (SUPERADMIN_REQUIRED) |
| superadmin | evet |

---

## Cache güvenliği

In-process public feed cache (`public:listings:*`).  
Approve/reject/edit → invalidate.  
Serve sırasında status hard-filter: PENDING asla sızmaz.

---

## Fail-safe

| AI sorunu | Sonuç |
|-----------|--------|
| timeout / unavailable | MODERATION_UNAVAILABLE |
| malformed confidence | MODERATION_UNAVAILABLE |
| CHILD_SAFETY / trafficking BLOCKED | REJECTED + CRITICAL |

---

## Kullanıcı mesajları

- İnceleme: “İçeriğiniz incelemeye gönderildi.”
- Approved: “Takasa açıldı.”
- Rejected: “İçeriğiniz Change X kurallarına uygun bulunmadı.”
- Edit: “İçeriğinizde düzenleme gerekiyor.”

---

## Flutter

- Create snackbar: inceleme mesajı
- Superadmin: **MODERASYON** kuyruğu (LOW/MEDIUM/HIGH/CRITICAL)

---

## Kalan riskler

- Heuristic ≠ production vision model — harici provider bağlanmalı
- Photo URL içerik indirilmeden analiz
- Cache process-local (multi-worker share yok)
- Otomatik kalıcı ban yok (risk score + Superadmin SUSPEND)
- Change Chain henüz yok (gate stub var)

---

## Sonuç

**116/116 test geçti.** Baseline 94 korundu; Trust & Safety 22 yeni test.  
Onaysız listing public/offer/trade/chain kapılı; AI kör yayın yapamaz; Superadmin nihai otorite.
