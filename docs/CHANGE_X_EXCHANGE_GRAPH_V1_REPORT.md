# CHANGE X EXCHANGE GRAPH V1 REPORT

**Başarı kriteri:** Change Chain için güvenli ve yapılandırılmış veri altyapısı hazır.  
**Change Chain algoritması implement edilmedi.**

---

## Test sonuçları

| Suite | Sonuç |
|-------|--------|
| Baseline (Core + Trust & Safety) | **116 passed** (korundu) |
| Exchange Graph V1 | **23 passed** |
| **TOPLAM** | **139 passed / 0 failed** |

Komut: `PYTHONPATH=/workspace pytest changex/tests -q`

---

## Domain model

### ModerationStatus (ayrı domain)
`DRAFT` · `PENDING_MODERATION` · `AI_REVIEW` · `ADMIN_REVIEW` · `MODERATION_UNAVAILABLE` · `APPROVED` · `REJECTED` · `EDIT_REQUIRED` · `ESCALATED` · `SUSPENDED`

### InventoryStatus / listing lifecycle (ayrı domain)
`AVAILABLE` · `RESERVED` · `TRADED` · `CANCELLED` · `EXPIRED`

### Migration stratejisi (geriye uyumlu)
- Legacy tek kolon `status` **korundu** (mevcut 116 testi bozmamak için)
- Yeni kolonlar: `moderation_status`, `inventory_status`
- `db.sync_dual_status()` her kritik transition’da iki domain’i hizalar
- Idempotent backfill: `split_from_legacy_status()`

Uzun vadede API tamamen dual status’e geçebilir; şu an projection ile legacy `status` üretilir.

---

## Structured wants (HAVE/WANT)

`wanted_items` free-text **korundu**.

Yeni alanlar:
- `wanted_categories`, `wanted_subcategories`, `wanted_brands`, `wanted_locations`
- `wanted_value_min`, `wanted_value_max` (mandal)
- `value_gap_tolerance` (izin verilen gap — otomatik “yakınsa uygundur” değil)

Validasyon: `validate_structured_want()` — max&lt;min, negatif, overflow reddedilir.

---

## Structured offers

Normalize alanlar:
- `category`, `subcategory`, `brand`, `model_name`, `condition`
- `location` + `location_city` / `district` / `country` (GPS yok; privacy)
- `mandal_units`, `attributes` (PII anahtarları strip)

---

## Chain opt-in & preferences

| Alan | Default |
|------|---------|
| `chain_opt_in` | `false` |
| `trade_preference` | `DIRECT_ONLY` |
| User prefs table | `matching_preferences` |

`DIRECT_ONLY` → chain candidate değil  
`CHAIN_ALLOWED` + opt-in + APPROVED + AVAILABLE → yapısal candidate (algoritma yok)

---

## Value tolerance

Ayrı kavramlar:
- listing min/max kabul (`min_mandal_units` / `max_mandal_units`)
- want value range
- `value_gap_tolerance`

Kategori/want uyumu olmadan yalnızca değere bakılmaz (scoring contract bunu ayırır).

---

## Category compatibility

Versioned: `CHANGE_X_CATEGORY_COMPAT_V1`  
Default: yalnızca same-category edges (hard-coded iş kuralı dayatması yok).  
`CategoryCompatibility` + opsiyonel `category_compatibility` tablo iskeleti.

---

## Location normalization

- Free-text `location` korundu
- `location_city` (location’dan kaba türetim mümkün)
- GPS / lat-lon **toplanmıyor**
- Matching preference API PII sızdırmaz

---

## Matching abstraction

- `ScoreProvider` / `ScoreBreakdown` (category, value, want, location, condition, preference)
- `MatchCandidate` modeli — `graph_edge_materialized=false`, `chain_algorithm=NOT_IMPLEMENTED`
- `is_public_matchable` / `is_chain_candidate` / `matchability_report`
- AI skor tek otorite değil; deterministic gates ayrı

---

## APPROVED / inventory gates

Matchable yalnız:
1. `moderation_status = APPROVED`
2. `inventory_status = AVAILABLE`
3. (chain için) `chain_opt_in` + `CHAIN_ALLOWED`

Blocked: RESERVED, TRADED, CANCELLED, EXPIRED, SUSPENDED, unapproved.

Trust & Safety: AI SAFE ≠ APPROVED (değişmedi).

---

## Indexes (planlı / uygulanan)

- `idx_listings_matchability (moderation_status, inventory_status, chain_opt_in, category)`
- `idx_listings_value_cat (category, mandal_units)`

Premature over-index yok.

---

## APIs

| Endpoint | Not |
|----------|-----|
| `GET /api/matching/preferences` | opt-in / preference (PII yok) |
| `PATCH /api/matching/preferences` | auth zorunlu |
| `GET /api/listings/{id}/matchability` | owner/staff |
| `POST /api/change-chain/match` | `CHANGE_CHAIN_ENABLED=false` → `501 CHANGE_CHAIN_DISABLED` |

---

## Feature flag

`CHANGE_CHAIN_ENABLED` env (default **false**).  
Production’da false. Kullanıcı gerçek Chain sonucu alamaz.

---

## Planned events (üretilmiyor)

`MATCH_CANDIDATE_CREATED`, `CHAIN_CANDIDATE_CREATED`, `ASSET_LOCKED`, …  
Exchange Graph V1’de emission yok — tasarım notu `domain_status.PLANNED_CHAIN_EVENTS`.

---

## Bu görevde YAPILMAYANLAR

- cycle detection / graph traversal / path search
- multi-party settlement / Asset Lock
- chain acceptance / completion
- automatic chain matching

---

## Kalan riskler

- Legacy `status` ile dual kolon senkron drift riski → `sync_dual_status` disiplinine bağlı
- Compatibility matrix henüz admin UI’siz
- Structured want adoption (eski free-text listingler zayıf sinyal)
- Gerçek Chain latency/index ihtiyaçları henüz ölçülmedi

---

## Sonuç

**139/139 test geçti.**  
Baseline 116 korundu.  
**Change Chain implemented değildir.**  
Exchange Graph V1: structured HAVE/WANT, dual moderation/inventory status, opt-in, scoring contract, feature-flagged gate — Chain için güvenli veri altyapısı hazır.
