# BenimBazar

KKTC odaklı araç marketplace — **PHP 8.1+ / MySQL** (Natro / cPanel).

| | |
|---|---|
| **Marka** | BenimBazar |
| **Canlı** | http://changex.mehmetfer.com.tr |
| **Kaynak** | `php-site/` |
| **Stack** | Sunucu tarafı PHP sayfaları — **Flutter ve ayrı REST API yok** |

## Proje yapısı

```
php-site/          Canlı site kaynak kodu (cPanel public_html)
scripts/           Deploy, canlıdan çekme, import araçları
docs/              Audit ve teknik notlar
```

## Yerel geliştirme

```powershell
cd D:\changex\php-site
php -S localhost:8080
```

- `config/database.local.php` — yerel MySQL (git'e eklenmez)
- `config/google.local.php` — OAuth (git'e eklenmez)
- Canlıdan çekme: `python scripts/pull_live_http.py`

## Admin

- `/admin/` — ilan moderasyonu
- `/admin/users.php` — kullanıcılar / roller
- `/admin/vip-kurumsal.php` — VIP Kurumsal galeri yönetimi (superadmin)

## cPanel kurulum

Ayrıntı: `php-site/KURULUM.txt`

1. `php-site/` dosyalarını site köküne yükleyin
2. `kurulum.php` veya SQL import ile migrate
3. `config/database.php` sunucuda oluşturulur

## Deploy

```powershell
python scripts/deploy_rebrand_http.py
```

Deploy doğrulama: `php-site/deploy-ping.txt`

## Canlı denetim (2026-08-17)

| URL | Beklenen |
|-----|----------|
| `/` | PHP ana sayfa, başlık **BenimBazar** |
| `/main.dart.js`, `/api/` | **410 Gone** (yeni `.htaccess` deploy sonrası) |
| `/php/proxy.php` | 404 |
| `/info.php` | 404 (production) |

Canlıda Flutter dosyası yok; eski yollar rewrite ile ana sayfaya düşüyordu — `.htaccess` güncellemesi 410 döndürür.

## Geçmiş

Repo geçmişinde ChangeX / Koca_Kafa (Flutter + Python) vardı; **aktif ürün yalnızca BenimBazar PHP** sitesidir.
