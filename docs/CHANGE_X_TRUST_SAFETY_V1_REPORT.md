# CHANGE X TRUST & SAFETY V1 REPORT

AI Ön Moderasyon + Superadmin Nihai Yayın Onayı

**İlke:** AI yayın kararının sahibi değildir. Superadmin nihai yayın otoritesidir.

---

## Test sonuçları

| Suite | Sonuç |
|-------|--------|
| Önceki (Core V1 + V1.1) | 94 |
| Trust & Safety V1 | 16 |
| **TOPLAM** | **110 passed / 0 failed** |

Komut: `PYTHONPATH=/workspace pytest changex/tests -q`

---

## Moderation architecture

```
USER create listing
  → PENDING_MODERATION
  → AI pre-moderation (ModerationProvider)
  → ADMIN_REVIEW | MODERATION_UNAVAILABLE | REJECTED(CSAM)
  → Superadmin decision
  → APPROVED | REJECTED | EDIT_REQUIRED | SUSPENDED
```

- Public feed / offer / Change Chain gate: **yalnızca APPROVED**
- AI `SAFE` olsa bile otomatik yayın **yok**
- AI unavailable → **fail-closed** (`MODERATION_UNAVAILABLE`), yayın yok

---

## Yeni listing state’leri

`DRAFT`, `PENDING_MODERATION`, `AI_REVIEW`, `ADMIN_REVIEW`, `MODERATION_UNAVAILABLE`, `APPROVED`, `REJECTED`, `EDIT_REQUIRED`, `SUSPENDED` + mevcut trade kilitleri (`RESERVED`, `TRADED`, …).

Legacy `ACTIVE` → migration ile `APPROVED`; kodda `ACTIVE` APPROVED ile eşdeğer okunur.

---

## Database değişiklikleri

- `trade_listings`: `moderation_version`, `ai_result`, `ai_confidence`, `ai_categories`, `ai_policy_version`, `risk_level`, `moderation_priority`, `moderation_reason`, `approved_at`, `approved_by`, …
- `listing_photos` (url + per-photo moderation_status + version)
- `moderation_reviews` (AI payload / policy_version)
- `moderation_decisions` (audit trail)
- `users.user_risk_score`, `users.suspended`

---

## API değişiklikleri

| Endpoint | Not |
|----------|-----|
| `POST /api/listings` | `PENDING_MODERATION` + AI; asla direkt APPROVED |
| `GET /api/listings` | yalnızca APPROVED |
| `GET /api/listings/mine` | sahibi tüm durumları görür |
| `GET /api/listings/{id}` | onaysızlar gizli (owner/staff hariç) |
| `PATCH /api/listings/{id}` | `status` set **yasak**; kritik alan → re-moderation |
| `POST /api/trades/offer` | `LISTING_NOT_APPROVED` |
| `POST /api/change-chain/match` | stub + unapproved block |
| `GET /api/admin/moderation/queue` | **SUPERADMIN** |
| `POST /api/admin/moderation/{id}/decision` | APPROVE/REJECT/REQUEST_EDIT/ESCALATE/SUSPEND_USER |
| `GET /api/admin/moderation/{id}/audit` | karar + audit |

---

## RBAC

| Rol | Yayın onayı | Queue |
|-----|-------------|-------|
| `user` | hayır | hayır |
| `admin` | hayır | hayır |
| `superadmin` | **evet** | **evet** |

---

## AI provider abstraction

`changex/app/moderation/provider.py`

- `ModerationProvider` protocol
- `HeuristicModerationProvider` (text + image URL heuristics)
- `UnavailableModerationProvider` (fail-safe test)
- `set_provider()` / `get_provider()` — business logic provider’dan bağımsız

Sonuçlar: `SAFE | REVIEW | HIGH_RISK | BLOCKED | UNAVAILABLE` + **confidence** + categories + `policy_version=CHANGE_X_SAFETY_V1`.

CSAM / insan ticareti → `BLOCKED` + listing `REJECTED` (yüksek güvenlik).

---

## Image moderation

- Create/edit `photo_urls` AI image check’e girer
- `listing_photos` satırları version’lı
- Superadmin APPROVE → fotoğraflar `APPROVED`
- Yeni fotoğraf / kritik edit → `moderation_version++` + tekrar kuyruk

---

## Admin queue / UI

- Backend queue: priority + AI + risk + owner risk + prior decisions
- Flutter: `ModerationQueueScreen` (LOW/MEDIUM/HIGH/CRITICAL görsel)
- Kullanıcı create sonrası: “İçeriğiniz incelemeye gönderildi.”

---

## Audit log

`moderation_decisions` + `audit_logs`: listing_id, moderator, role, previous/new status, decision, reason, ai_result, confidence, correlation_id, timestamp.

---

## Fail-safe

| Durum | Davranış |
|-------|----------|
| Provider exception / timeout | `MODERATION_UNAVAILABLE`, yayın yok |
| Confidence missing | unavailable yolu |
| AI SAFE | yine Superadmin kuyruğu |

---

## Kalan riskler

- Heuristic AI gerçek vision modeli değil; production’da harici provider bağlanmalı
- Photo URL’ler içerik indirmeden URL/context analizi
- Rate-limit in-memory (multi-worker share yok)
- Change Chain henüz yok (gate stub var)
- Otomatik kalıcı ban yok (risk score + suspend kararı Superadmin)

---

## Sonuç

**110/110 test geçti.** Onaysız listing public feed’de yok, offer/trade/Change Chain kapılı, AI kör yayın yapamıyor, Superadmin nihai otorite.
