# CHANGE X — Mimari Analiz & Migration Raporu

## Özet

Mevcut `Koca_Kafa` deposu BIST kağıt-üstü al/sat ürünleri içerir (`companion`, `borsa_bot`, `borsa_app`).  
**CHANGE X** bunları silmeden yanına eklenir: `changex/` (FastAPI) + Flutter kabuk (Varmisin → CHANGE X).

**Prensip:** PARA YOK · SATIN ALMA YOK · SADECE TAKAS  
Birimler: **Mandal / Dirhem / Madalyon** (1 Madalyon = 254 Dirhem = 64.516 Mandal).

## Mevcut durum (analiz)

| Katman | Durum |
|--------|--------|
| Auth (repo) | Yoktu (companion/borsa açık API) |
| Auth (Varmisin) | Yerel SharedPreferences login vardı → API auth’a taşındı |
| DB | SQLite ledger (TRY cash) — borsa’ya özel |
| Frontend | companion HTML + Flutter borsa + Varmisin demo |
| Backend | FastAPI companion :8000 |

## Önerilen / uygulanan CHANGE X mimarisi

```
Flutter (CHANGE X UI)
    │  Bearer token
    ▼
FastAPI changex.app.main
    ├── /api/auth/*
    ├── /api/listings*
    ├── /api/trades*
    ├── /api/value/normalize   (sunucu tarafı)
    └── SQLite changex/data/changex.db
```

- Değer hesabı yalnızca backend (`value.py`)
- State machine (`states.py`) — geçersiz transition reddedilir
- Ziyaretçi: liste/arama; teklif/kayıt için login zorunlu

## Migration planı

1. ✅ Değer motoru + state machine + auth/listing/offer API  
2. ✅ Varmisin UI → CHANGE X (lobi/oyunlar → takas kayıtları)  
3. ⏳ Change Chain (A→B→C→D) algoritması  
4. ⏳ Admin paneli + Change Score motoru  
5. ⏳ Dosya yükleme / mesajlaşma / anlaşmazlık  

## Test planı

- `pytest changex/tests` — dönüşüm + state machine  
- Flutter widget smoke test  
- API: register → listing → offer → gap hesabı  

## Riskler

- Quick tunnel kararsız olabilir  
- Change Chain henüz yok  
- Fotoğraf yükleme henüz URL listesi stub  
- companion Borsa hâlâ repoda (bilinçli; bozulmasın diye silinmedi)
