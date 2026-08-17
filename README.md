# BenimBazar

KKTC odaklı araç marketplace — **PHP 8.1+ / MySQL** (Natro / cPanel).

| | |
|---|---|
| **Marka** | BenimBazar (eski ad: ChangeX) |
| **Canlı** | http://changex.mehmetfer.com.tr |
| **Kaynak** | `php-site/` |

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

1. `php-site/` dosyalarını site köküne yükleyin
2. `kurulum.php` ile kurulum / migrate (production'da dikkatli kullanın)
3. `config/database.php` sunucuda oluşturulur (repoda yok)

Ayrıntı: `php-site/KURULUM.txt`

## Deploy

```powershell
python scripts/deploy_rebrand_http.py
```

Deploy doğrulama: `php-site/deploy-ping.txt`

## GitHub

Repo geçmişinde **ChangeX / Koca_Kafa** (Flutter + Python) vardı; aktif ürün **BenimBazar PHP** sitesidir (`php-site/`).
