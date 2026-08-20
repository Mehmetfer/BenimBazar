<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

header('Content-Type: text/plain; charset=UTF-8');

$steps = [];

try {
    cx_bootstrap();
    $steps[] = '1 bootstrap: ok';

    $user = cx_require_staff();
    $steps[] = '2 staff: ok (' . (string) ($user['username'] ?? '') . ')';

    require_once dirname(__DIR__) . '/app/Services/AdminListingService.php';
    $svc = new \App\Services\AdminListingService();
    $steps[] = '3 AdminListingService: ok';

    $stats = $svc->stats();
    $steps[] = '4 stats: ok (total=' . (int) ($stats['total'] ?? 0) . ')';

    $probe = $svc->listProbe();
    $steps[] = '5 probe: raw=' . (int) $probe['raw']
        . ' joined=' . (int) $probe['joined']
        . ($probe['sample'] ? ' sample=' . $probe['sample'] : '')
        . ($probe['error'] ? ' ERR=' . $probe['error'] : '');

    $breakdown = $svc->statusBreakdown();
    $steps[] = '6 status: ' . json_encode($breakdown, JSON_UNESCAPED_UNICODE);

    $rows = $svc->list(null, null, 3);
    $listErr = \App\Services\AdminListingService::lastListError();
    $steps[] = '7 list: rows=' . count($rows)
        . ($listErr ? ' ERR=' . $listErr : '')
        . (count($rows) > 0 ? ' first=' . (string) ($rows[0]['title'] ?? '') : '');

    ob_start();
    $adminTab = 'listings';
    require dirname(__DIR__) . '/views/partials/admin-shell.php';
    $shell = ob_get_clean();
    $steps[] = '8 admin-shell: ok (' . strlen($shell) . ' bytes)';

    $content = '<p>ping layout test</p>';
    $title = 'Ping';
    $layout = 'admin';
    $bodyClass = 'page-admin';
    ob_start();
    require dirname(__DIR__) . '/views/layout.php';
    $layoutOut = ob_get_clean();
    $steps[] = '9 layout: ok (' . strlen($layoutOut) . ' bytes)';
} catch (Throwable $e) {
    $steps[] = 'HATA: ' . $e->getMessage();
    $steps[] = 'Dosya: ' . $e->getFile() . ':' . (int) $e->getLine();
}

echo implode("\n", $steps) . "\n";
