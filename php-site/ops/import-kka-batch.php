<?php

declare(strict_types=1);

/**
 * kibrisarabaal kuyrugundan toplu import — deploy secret ile korunur.
 * POST: secret, date_from, date_to, limit
 */
require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/ExternalListingImportService.php';
require_once dirname(__DIR__) . '/app/Services/ImportQueueService.php';
require_once dirname(__DIR__) . '/app/Services/ImportSourceRegistry.php';

use App\Services\ImportQueueService;
use App\Services\ImportSourceRegistry;

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST only']);
    exit;
}

$configPath = dirname(__DIR__) . '/config/deploy.local.php';
if (!is_file($configPath)) {
    http_response_code(503);
    echo json_encode(['ok' => false, 'error' => 'deploy.local.php yok']);
    exit;
}

/** @var array<string,mixed> $cfg */
$cfg = require $configPath;
$secret = (string) ($cfg['secret'] ?? '');
if ($secret === '' || !hash_equals($secret, (string) ($_POST['secret'] ?? ''))) {
    http_response_code(403);
    echo json_encode(['ok' => false, 'error' => 'secret']);
    exit;
}

$dateFrom = trim((string) ($_POST['date_from'] ?? '2026-08-01'));
$dateTo = trim((string) ($_POST['date_to'] ?? date('Y-m-d')));
$limit = min(50, max(1, (int) ($_POST['limit'] ?? 10)));

try {
    cx_bootstrap();
    $resolved = ImportSourceRegistry::resolve('kka');
    $svc = new ImportQueueService();
    $analysis = $svc->analyze(
        (string) $resolved['queue_dir'],
        (string) $resolved['domain'],
        $dateFrom,
        $dateTo
    );
    if ($analysis['pending'] === 0) {
        echo json_encode([
            'ok' => true,
            'imported' => 0,
            'pending' => 0,
            'message' => 'Bekleyen ilan yok',
            'analysis' => [
                'total' => $analysis['total'],
                'in_range' => $analysis['in_range'],
                'imported' => $analysis['imported'],
            ],
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $results = $svc->importBatch($resolved, $dateFrom, $dateTo, $limit, [
        'id' => 0,
        'username' => 'import-bot',
        'role' => 'superadmin',
    ]);
    $ok = count(array_filter($results, static fn (array $r): bool => $r['ok']));
    $fail = count($results) - $ok;

    echo json_encode([
        'ok' => true,
        'imported' => $ok,
        'failed' => $fail,
        'results' => $results,
        'date_from' => $dateFrom,
        'date_to' => $dateTo,
    ], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
}
