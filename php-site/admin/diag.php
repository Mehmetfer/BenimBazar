<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

header('Content-Type: text/plain; charset=UTF-8');

$steps = [];

try {
    cx_bootstrap();
    $steps[] = 'bootstrap: ok';

    $user = cx_require_staff();
    $steps[] = 'staff: ok (' . (string) ($user['username'] ?? '') . ')';

    require_once dirname(__DIR__) . '/app/Services/AdminListingService.php';
    $svc = new \App\Services\AdminListingService();
    $steps[] = 'AdminListingService: ok';

    $stats = $svc->stats();
    $steps[] = 'stats: ok (total=' . (int) ($stats['total'] ?? 0) . ')';

    $rows = $svc->list(null, null, 3);
    $steps[] = 'list: ok (rows=' . count($rows) . ')';

    $steps[] = 'cx_listing_days_live: ' . (function_exists('cx_listing_days_live') ? 'ok' : 'MISSING');
} catch (Throwable $e) {
    $steps[] = 'HATA: ' . $e->getMessage();
    $steps[] = 'Dosya: ' . $e->getFile() . ':' . (int) $e->getLine();
}

echo implode("\n", $steps) . "\n";
