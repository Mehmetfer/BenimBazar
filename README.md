# Borsa

Kağıt üstü **al–sat** uygulaması. Ollama yok.

## Çalıştır

```bash
bash scripts/install.sh
bash scripts/dev.sh
```

Aç: http://127.0.0.1:8000

Başlangıç nakdi: 100.000 TL (simülasyon)

## API

- `GET /api/market` — fiyatlar
- `GET /api/portfolio` — nakit, pozisyon, işlemler
- `POST /api/buy` `{ "symbol": "THYAO", "quantity": 10 }`
- `POST /api/sell` `{ "symbol": "THYAO", "quantity": 5 }`
- `POST /api/reset`
