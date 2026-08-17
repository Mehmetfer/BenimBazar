<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/KibrisArabaAlImportService.php';

use App\Services\KibrisArabaAlImportService;

cx_bootstrap(false);

$queueDir = dirname(__DIR__) . '/storage/kka-queue';
$svc = new KibrisArabaAlImportService();
$status = $svc->queueStatus($queueDir);

if ($status['next'] === null) {
    fwrite(STDERR, "Kuyrukta bekleyen ilan yok.\n");
    exit(1);
}

try {
    $result = $svc->importOne($status['next']);
    echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) . "\n";
    exit($result['skipped'] ?? false ? 0 : 0);
} catch (Throwable $e) {
    fwrite(STDERR, $e->getMessage() . "\n");
    exit(1);
}
