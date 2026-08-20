<?php
declare(strict_types=1);

/**
 * config.example.php -> config.php olarak kopyalayin.
 * cPanel: data/changex.db yolunu ve site_url ayarlayin.
 */
return [
    'site_name' => 'BenimBazar',
    'site_url' => 'http://changex.mehmetfer.com.tr',
    'db_path' => __DIR__ . '/data/changex.db',
    'listing_no_base' => 1_000_000_000,
    'session_cookie' => 'changex_token',
    'session_days' => 30,
    'uploads_path' => __DIR__ . '/uploads',
    'uploads_url' => '/uploads',
];
