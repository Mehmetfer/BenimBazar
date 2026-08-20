# BenimBazar — Yedek Anlık Görüntü (19 Ağustos 2026)

## Canlı durum
- Site: http://changex.mehmetfer.com.tr
- Son deploy tag: deploy-105647 (tam site) + sonraki parça deploy'lar
- SEO: landing noindex düzeltmesi, `/arac/otomobil/{marka}` 503 fix

## kibrisarabaal import
- Tarih: 1–19 Ağustos 2026
- Kuyruk: 28 ilan (km/renk esnetildi, GBP/TRY ayrımı)
- Canlı listing ID: 214–241
- Script: `scripts/kibrisarabaal_build_queue.py`, `scripts/kka_upload_queue.py`
- Ops: `php-site/ops/import-kka-batch.php`, `php-site/ops/cancel-listing.php`

## Önemli yeni modüller
- SEO: seo-core, seo-routes, seo-meta, robots.php, sitemap
- Import: ExternalListingImportService, ImportQueueService, admin/import.php
- VIP kurumsal galeri import profili

## Hariç tutulan (güvenlik)
- scripts/ftp-credentials.local.json
- php-site/config/database*.php (local)
- php-site/config/deploy.local.php
