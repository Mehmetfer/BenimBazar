# CHANGE X CORE V1 REPORT

## Özet

A↔B takas çekirdeği production-grade hale getirildi. **Change Chain implement edilmedi.**

Test sonucu: **`30 passed`** (`pytest changex/tests`)

## Değiştirilen dosyalar

- `changex/app/value.py` — `ChangeValue` value object
- `changex/app/states.py` — ListingStatus + TradeState transitions
- `changex/app/db.py` — `mandal_units`, version, audit alanları, migrations, BEGIN IMMEDIATE
- `changex/app/main.py` — authz, offer/accept/cancel/confirm/complete, structured errors
- `changex_app` / Flutter screens — kategoriler + listing-id offer akışı
- `scripts/*`, `.cursor/environment.json` — CHANGE X boot (önceki)

## Eklenen dosyalar

- `changex/app/engine.py` — atomic offer/accept/complete/cancel
- `changex/tests/test_core_v1.py` — value/listing/offer/concurrency/state/atomic tests
- `docs/CHANGE_X_CORE_V1_REPORT.md` (bu dosya)

## Database migrations

SQLite idempotent migrate:

- `trade_listings.mandal_units` (canonical integer)
- `trade_listings.version`, `updated_at`, `status` (ACTIVE/RESERVED/TRADED/…)
- `listing_items.mandal_units`
- `trades` offer alanları: proposer/receiver, listing id listeleri, gap, expires/accepted/cancelled/completed, version
- `idempotency_keys`
- `audit_logs.entity`, `entity_id`, `correlation_id`

## API değişiklikleri

Korunan:
- `/api/auth/*`, `/api/listings`, `/api/health`, `/api/trades/offer`, `/api/trades/mine`

Güçlenen / yeni:
- `POST /api/trades/offer` → `requested_listing_ids` + `offered_listing_ids` (sunucu değer yeniden hesaplar)
- `POST /api/trades/{id}/accept|cancel|confirm|complete` (+ idempotency_key)
- `PATCH /api/listings/{id}` ownership kontrollü
- Hatalar: `{code, message}`

## State machine

Valid path örneği: OFFERED → ACCEPTED → CONFIRMED → IN_TRANSFER → DELIVERED → COMPLETED  
Engellenen: COMPLETED→OFFERED, CANCELLED→ACCEPTED, EXPIRED→ACCEPTED

## Güvenlik

- Negatif / float değer reject
- Ownership authz (listing update, cancel, accept)
- RESERVED listing ikinci accept’te CONFLICT
- Atomic ownership swap + rollback
- Idempotency keys (accept/cancel/confirm/complete/offer)
- Audit log kritik aksiyonlarda
- Rate limit (testlerde izole)

## Testler

| Sonuç | Adet |
|--------|------|
| Geçen | **30** |
| Başarısız | **0** |

Kapsam: conversion edges, negative/float/overflow, gap display, listing ownership, multi-listing offer, unauthorized cancel, atomic complete + idempotency, concurrent accept race, guest authz, health domain.

## Flutter UI

- Kategoriler: TÜM TAKASLAR / POPÜLER / YENİ / YAKININDA / HIZLI TAKAS
- Marka: CHANGE X · TAKAS EKOSİSTEMİ
- Teklif: önce listing oluştur → listing id ile offer (backend recalc)

## Kalan riskler

- Fotoğraf upload yok (URL stub)
- Change Score henüz kural motoru değil (alan var)
- Admin paneli minimal (`/api/admin/stats`)
- Mesajlaşma / dispute UI yok
- Flutter widget test timer flake (API splash) — backend suite yeşil
- Eski DB dosyası varsa migrate çalışır; temiz kurulum önerilir

## Change Chain için hazır olmayan noktalar

- Çok taraflı graph matching yok
- Zincir state machine / all-party consent yok
- Cycle detection / dead-lock çözümü yok
- Escrow çoklu taraflı release yok

**Sonraki adım:** A↔B metrikleri + load test sonrası Change Chain tasarımı.
