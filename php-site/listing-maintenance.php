<?php

declare(strict_types=1);

/** Ilan suresi bakimi — cron veya manuel: /listing-maintenance.php?key=... */
require __DIR__ . '/bootstrap.php';

$cfg = cx_app_config();
$expected = (string) ($cfg['maintenance_key'] ?? 'changex-maint');
$key = (string) ($_GET['key'] ?? '');

if ($key === '' || !hash_equals($expected, $key)) {
    http_response_code(403);
    exit('Forbidden');
}

cx_bootstrap();
\App\Services\ListingLifecycleService::runMaintenance();
header('Content-Type: text/plain; charset=utf-8');
echo 'OK ' . date('c');
