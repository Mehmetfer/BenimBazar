# BenimBazar (PHP)

KKTC odaklı araç marketplace — **PHP 8.1+ / MySQL** (Natro / cPanel).

Canlı: http://changex.mehmetfer.com.tr

## Proje yapısı

```
php-site/          Kaynak kod (cPanel köküne yüklenir)
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
- Canlı senkron: `python scripts/pull_live_http.py`

## cPanel kurulum

1. `php-site/` dosyalarını site köküne yükleyin
2. `kurulum.php` ile kurulum / migrate (production'da dikkatli kullanın)
3. `config/database.php` sunucuda oluşturulur (repoda yok)

Ayrıntı: `php-site/KURULUM.txt`

## Deploy

```powershell
python scripts/deploy_rebrand_http.py
```

Deploy doğrulama: `php-site/deploy-ping.txt` → `deploy-021525`
