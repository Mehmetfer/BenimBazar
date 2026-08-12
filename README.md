# CHANGE X

Para yok. Satın alma yok. **Sadece takas.**

Platform birimleri: **Mandal · Dirhem · Madalyon**  
(1 Madalyon = 254 Dirhem = 64.516 Mandal — gerçek para değildir)

## Çalıştır

```bash
bash scripts/install.sh
bash scripts/start.sh
```

Aç: http://127.0.0.1:8000

## API (özet)

- `POST /api/auth/register|login`
- `GET /api/listings` (ziyaretçi OK)
- `POST /api/listings` (login)
- `POST /api/trades/offer` (login)
- Değer hesabı sunucuda (`changex/app/value.py`)

## Mimari

Detay: `docs/CHANGE_X_ARCHITECTURE.md`

Flutter kaynak: `changex_app/`  
Backend: `changex/`
