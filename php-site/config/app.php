<?php
return [
    'name' => 'BenimBazar',
    'tagline' => 'Al, sat, kazançlı çık!',
    'url' => 'http://changex.mehmetfer.com.tr',
    'timezone' => 'Europe/Istanbul',
    'locale' => 'tr_TR',
    'charset' => 'UTF-8',
    'debug' => false,
    /** Canli sunucuda true; yerel gelistirmede false yapin (kurulum.php / test.php acilir). */
    'production' => true,
    /** Mesajlaşma (Aşama 2). */
    'messages_enabled' => true,
    /** true yapinca superadmin icin bilinen zayif sifreler (14531453 vb.) engellenir. */
    'block_weak_superadmin_password' => false,
    'session_name' => 'changex_session',
    'session_lifetime' => 86400 * 30,
    'session_path' => '/',
    'session_domain' => '',
    'session_secure' => null,
    'session_samesite' => 'Lax',
    'session_save_path' => __DIR__ . '/../storage/sessions',
    'listing_no_base' => 1000000000,
    'listing_ttl_days' => 90,
    'feed_limit' => 120,
    'view_salt' => 'changex-view-v1',
    'uploads_path' => __DIR__ . '/../uploads',
    'uploads_url' => '/uploads',
    'max_upload_bytes' => 5 * 1024 * 1024,
    'allowed_upload_types' => ['image/jpeg', 'image/png', 'image/webp'],
    'brand_assets' => [
        'logo_horizontal' => '/assets/branding/logo-horizontal-transparent.png',
        'logo_vertical' => '/assets/branding/logo-vertical-transparent.png',
        'logo_icon' => '/assets/branding/logo-icon.png',
        'favicon' => '/assets/branding/favicon-512.png',
        'favicon_32' => '/assets/branding/favicon-32.png',
        'watermark' => '/assets/branding/watermark-logo.png',
    ],
    /** Filigran: upload aninda dosyaya yazilir; CSS katmani kapali. */
    'photo_watermark' => [
        'enabled' => false,
        'burn_on_upload' => true,
        'logo' => '/assets/branding/watermark-logo.png',
        'burn_logo' => '/assets/branding/watermark-logo.png',
        'burn_width_ratio' => 0.18,
        'burn_opacity' => 30,
        'burn_margin_px' => 14,
        'burn_blur_passes' => 2,
        'burn_jpeg_quality' => 88,
        'opacity_detail' => 0,
        'opacity_card' => 0,
        'opacity_thumb' => 0,
        'blur_px' => 0,
        'rotate_deg' => 0,
    ],
    /** Telefon dogrulama (Asama 4). mode=debug: kod ekranda; live: SMS/WhatsApp API. */
    'phone_verify' => [
        'required' => false,
        'mode' => 'debug',
        'default_channel' => 'whatsapp',
        'code_ttl_seconds' => 300,
        'max_send_per_hour' => 5,
        'max_attempts' => 5,
    ],
    /** Ilan kalitesi (Asama 5). */
    'listing_quality' => [
        'enabled' => true,
        'min_photos' => 3,
        'min_description_chars' => 80,
        'min_title_chars' => 10,
        'require_price_on_sale' => true,
        'feed_require_vehicle_attrs' => true,
        'feed_min_photos' => 1,
        'min_score_submit' => 0,
    ],
    /** Benzer ilanlar — detay sayfasi (Asama 6). */
    'similar_listings' => [
        'enabled' => true,
        'limit' => 6,
    ],
    /** Ilan siralama — ana feed (Asama 7). */
    'listing_sort' => [
        'enabled' => true,
        'default' => 'date_desc',
    ],
    /** SEO landing — sehir / marka (Asama 8). */
    'seo_landing' => [
        'enabled' => true,
        'popular_brands_per_segment' => 15,
    ],
    /** Galeri kesfi (Asama 9). */
    'gallery_discovery' => [
        'enabled' => true,
        'featured_vip' => 6,
        'featured_dealer' => 6,
        'per_page' => 24,
    ],
    /** Fiyat dusus alarmlari. */
    'price_drop_alerts' => [
        'enabled' => true,
        'dedup_seconds' => 86400,
        'email' => true,
    ],
    /** Kibris piyasa karsilastirmasi (Asama 11). */
    'market_compare' => [
        'enabled' => true,
        'min_samples' => 4,
        'max_fetch' => 200,
        'year_tolerance' => 2,
        'avg_band_pct' => 8.0,
        'segments' => ['otomobil', 'motosiklet', 'ticari', 'antika-arac'],
    ],
    /** SEO varsayilanlari — admin panelinden storage/seo-settings.json ile genisletilir. */
    'seo' => [
        'default_title' => 'BenimBazar | Türkiye ve KKTC Araç İlanları',
        'default_description' => 'BenimBazar ile Türkiye ve KKTC\'de otomobil, motosiklet, bisiklet ve ticari araç ilanlarını keşfedin. Araç ilanı verin, satın veya takas seçeneklerini değerlendirin.',
        'search_url_template' => '/index.php?q={search_term_string}',
    ],
    /**
     * Ana sayfa ilan grid reklam slotu.
     * sponsored: storage/feed-ads.json veya buradan — kullanici/sponsor reklamlari.
     */
    'feed_ads' => [
        'enabled' => true,
        'insert_after' => 4,
        'rotate_interval_ms' => 7000,
    ],
];
