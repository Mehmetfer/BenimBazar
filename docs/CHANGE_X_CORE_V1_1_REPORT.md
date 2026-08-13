# CHANGE X CORE V1.1 REPORT

Stress Test + Concurrency + Production Hardening

**Change Chain implement edilmedi.** Para / payment / cash settlement yok.

## Test özeti

| Suite | Sonuç |
|-------|--------|
| BASELINE (`test_core_v1.py`) | **30 passed** |
| NEW SUITE (V1.1 stress/idempotency/abuse/fuzz/load) | **64 passed** |
| TOTAL | **94 passed / 0 failed** |

Komut: `PYTHONPATH=/workspace pytest changex/tests -q`

---

## 1–3. Toplam / geçen / başarısız

1. **Toplam test:** 94  
2. **Geçen:** 94  
3. **Başarısız:** 0  

---

## 4. Concurrency sonucu

| Senaryo | Sonuç |
|---------|--------|
| Aynı `trade_id` üzerinde eşzamanlı `accept` | Tek `OFFERED→ACCEPTED` event; ikinci 409 CONFLICT veya güvenli ACCEPTED replay |
| Aynı listing iki trade’e (double-spend) | `200 + 409`; listing tek kazanan trade’e RESERVED/TRADED |
| Paylaşılan listing C (A+B↔C vs D↔C) | Tek accept; kaybeden taraf listing’leri ACTIVE kaldı — **partial settlement yok** |

---

## 5. Idempotency sonucu

`offer` / `accept` / `cancel` / `confirm` / `complete` için aynı key ile **2 / 5 / 10 / 50** tekrar:

- Tek logical trade / tek state transition
- Duplicate trade oluşmadı
- Lost-response retry (accept commit sonrası aynı key) güvenli replay

---

## 6. Rollback sonucu

Failure injection: ilk listing `RESERVED` sonrası `RuntimeError`.

- Trade `OFFERED` kaldı  
- Her iki listing `ACTIVE`  
- `offer.accept` audit commit edilmedi  
- SQLite `BEGIN IMMEDIATE` + rollback doğrulandı  

---

## 7. SQLite lock sonucu

Yapılandırma:

- `journal_mode=WAL`
- `busy_timeout=30000`
- `BEGIN IMMEDIATE` + busy retry (max 8)
- `synchronous=NORMAL`

Load / contention ölçümleri (process-local `LOCK_STATS`):

| Profile | begin_immediate | busy_retries | busy_failures | commits |
|---------|-----------------|--------------|---------------|---------|
| baseline (10) | 20 | 0 | 0 | 20 |
| medium (50) | 100 | 0 | 0 | 100 |
| heavy (100) | 200 | 0 | 0 | 200 |
| stress (250) | 500 | 0 | 0 | 500 |

Process crash simülasyonu: orphan `RESERVED` → `/api/admin/recover` ile ACTIVE’e dönüş.

---

## 8–12. Load test + latency + error rate

Ortam: in-process FastAPI `TestClient` + thread pool (gerçek ağ yok; motor + SQLite ölçümü).

| Profile | Users | req/s | p50 (ms) | p95 (ms) | p99 (ms) | error_rate | timeouts | ok trades | rejected/cancel |
|---------|-------|-------|----------|----------|----------|------------|----------|-----------|-----------------|
| baseline | 10 | ~377 | ~12 | ~42 | ~54 | 0.0 | 0 | 5 | 5 |
| medium | 50 | ~381 | ~58 | ~179 | ~277 | 0.0 | 0 | 25 | 25 |
| heavy | 100 | ~250 | ~88 | ~689 | ~1081 | 0.0 | 0 | 50 | 50 |
| stress | 250 | ~151 | ~179 | ~1397 | ~1745 | 0.0 | 0 | 125 | 125 |

Ham JSON: `changex/data/load_test_results.json`

---

## 13. Rate limit sonucu

IP + endpoint (+ user) kovaları doğrulandı:

- `register` → 429 (`RATE_LIMIT`)
- `login` → 429 (`RATE_LIMIT`)
- listing create / offer / accept / cancel için endpoint bazlı limitler aktif

---

## 14. Abuse test sonucu

Hepsi güvenli red:

- Başkasının listing update → 403  
- Başkasının trade accept → 403  
- Başkasının offer cancel → 403  
- Sahte / negatif / float value → 400/422  
- Başkasının listing’ini offered gösterme → 403  
- Expired accept → 409 `OFFER_EXPIRED`  
- Completed tekrar complete → güvenli no-op  
- TRADED listing reuse → 409  

---

## 15. Value fuzz sonucu

0, 1, 253–255, 64515–64517, overflow, negatif, float, string, null, malformed, bool, list — canonical `mandal_units` bozulmadı; geçersizler yalnızca `ChangeValueError`.

---

## 16. Bulunan buglar

1. Idempotency stress (50×) altında endpoint rate limit false-positive (test/limit etkileşimi)  
2. `create_offer` yazma yolu `BEGIN IMMEDIATE` dışında idi (concurrent idempotency yarışı riski)  
3. SQLite `busy_timeout` PRAGMA eksikti  
4. Orphan `RESERVED` recovery yolu yoktu  
5. Observability/metrics admin yüzeyleri yoktu  

---

## 17. Düzeltilen buglar

1. Offer yolu `immediate_tx` + idempotent UNIQUE replay  
2. `PRAGMA busy_timeout=30000` + busy retry sayaçları  
3. Accept ortası failure hook ile rollback kanıtı  
4. `recover_stale_reservations` + `/api/admin/recover`  
5. Correlation-id middleware + güvenli log alanları  
6. Domain metrics (`/api/admin/metrics`)  
7. Rate limit boyutları IP / user / endpoint ayrıldı  

---

## 18. Kalan riskler

- Tek SQLite writer: yüksek yazma RPS’te p99 büyür (stress ~1.7s)
- `TestClient` thread modeli gerçek HTTP/proxy latency’sini temsil etmez
- Stale RESERVED recovery admin tetiklemeli (otomatik cron yok)
- Change Chain / ASSET LOCK henüz yok — çok taraflı kilit modeli eksik
- In-memory rate limit process-local (multi-worker’da paylaşılmaz)

---

## 19. SQLite scalability değerlendirmesi

**Bu aşamada SQLite yeterli** — A↔B motoru için:

| Trafik bandı | Değerlendirme |
|--------------|---------------|
| ≤ ~50 eşzamanlı yazma odaklı kullanıcı | Rahat (p95 &lt; 200ms bu ortamda) |
| ~100 concurrent | Kullanılabilir; p99 ~1s’e çıkabilir |
| ~250 concurrent write-mix | Doğruluk korunuyor (0 error / 0 busy_failure); latency bozuluyor |
| Binlerce concurrent writer / multi-region | SQLite uygun değil → ileride Postgres + row locks |

Öneri: PostgreSQL migration **şimdi yapılmadı**; Change Chain / çok node öncesi planlanmalı.

---

## 20. Change Chain için veri eksikleri

Mevcut (kısmen hazır):

- `wanted_items` (serbest metin)
- `accept_categories`
- `min_mandal_units` / `max_mandal_units`
- `category` / `subcategory` / `location`
- trade events + audit + correlation_id
- domain metrics iskeleti

Eksik / zayıf (Chain öncesi gerekli):

| Alan | Durum |
|------|--------|
| Yapılandırılmış “ne istiyor?” (listing/kategori hedefleri) | Yok (yalnızca free-text) |
| Yapılandırılmış “ne teklif ediyor?” tercih listesi | Yok |
| Kategori uyumluluk matrisi / kuralları | Yok |
| Takas tercihi (sadece A↔B vs zincir) | Yok |
| `chain_opt_in` / zincire izin flag | Yok |
| ASSET LOCK (çok taraflı kilit) state | Yok (yalnızca RESERVED iki taraflı) |
| Zincir aday skoru / path arama indeksi | Yok |
| Lokasyon mesafe / bölge tercihi | `location` string var; geo yok |
| Minimum kabul edilebilir gap politikası | Alan var; enforce zayıf |

**Para yok:** ileride zincir için kavram **ASSET LOCK** olacak; monetary escrow / TL farkı yok.

---

## Domain metrikleri

`GET /api/admin/metrics` (admin):

- Offer Conversion (OFFERED→ACCEPTED+)
- Completion Rate (ACCEPTED+→COMPLETED)
- Cancellation Rate
- Dispute Rate
- Average Trade Value (mandal)
- Average Gap
- Time To Trade

Change Score / Chain için event yapısı hazır (`trade_events`, audit, correlation_id).

---

## Observability

Her response: `X-Correlation-Id`  
Log alanları: request/action, actor_id, entity, duration_ms, result, error_code  
**Loglanmayan:** password, token, secret, PII gövdeleri

---

## Sonuç

A↔B motoru yalnızca fonksiyonel değil; eşzamanlı accept/double-spend/multi-listing race, idempotency stress, rollback, abuse/fuzz ve kontrollü load altında **94/94** yeşil.

Bu rapor “production ready” iddiası taşımaz; ölçülen sonuç: **V1.1 stress hedefleri bu ortamda geçti**, SQLite tek-node yazma bandında doğruluk korunuyor, Change Chain hâlâ bilinçli olarak kodlanmadı.
