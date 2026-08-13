# CHANGE X

Para yok. Satın alma yok. **Sadece takas.**

Platform birimleri: **Mandal · Dirhem · Madalyon**  
(1 Madalyon = 254 Dirhem = 64.516 Mandal — gerçek para değildir)

[![CI](https://github.com/Mehmetfer/Koca_Kafa/actions/workflows/ci.yml/badge.svg)](https://github.com/Mehmetfer/Koca_Kafa/actions/workflows/ci.yml)

## Çalıştır

```bash
bash scripts/install.sh
bash scripts/start.sh
```

Aç: http://127.0.0.1:8000

## CI

Pull request’lerde GitHub Actions şunları çalıştırır:

- CHANGE X `pytest` (`changex/tests`)
- Security regresyon suite
- Image E2E + API E2E suite’leri
- Flutter `analyze` + `test` (`changex_app`)
- Düz `pytest --collect-only` (borsa_bot `PYTHONPATH` dahil collection hatası olmamalı)

Tek kontrol noktası: workflow job **`CI Gate`**.  
Merge’i kilitlemek için GitHub’da `main` branch protection’da **Require status checks → `CI Gate`** seçilmelidir (Actions’ın en az bir kez çalışmış olması gerekir).

Python bağımlılıkları `requirements.lock.txt` ile pin’lidir. Flutter için `changex_app/pubspec.lock` commit’lidir. Secret / production credential commit edilmez (`.env` gitignore’dadır; örnek: `borsa_bot/.env.example`).

## Self-verification (F7 foundation)

Controlled sandbox loop only — **no production mutate, no self-deploy, no LIVE autonomy**:

```bash
bash scripts/self_verify.sh
pytest self_verification/tests -q
```

Stages: OBSERVE → DETECT → DIAGNOSE → PLAN → PROPOSE → SANDBOX APPLY → TEST → VERIFY → ROLLBACK|READY_FOR_REVIEW → REPORT (audit JSONL).

## Test (lokal)

```bash
bash scripts/install.sh
source .venv/bin/activate
pytest                 # kök pytest.ini: pythonpath=. borsa_bot
pytest changex/tests -q
cd changex_app && flutter pub get && flutter analyze && flutter test
```

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
