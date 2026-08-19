<?php

declare(strict_types=1);

/**
 * Tek seferlik ilan iptali — deploy secret ile korunur.
 * Kullanim: POST secret + listing_id
 */
require dirname(__DIR__) . '/bootstrap.php';

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

$listingId = (int) ($_POST['listing_id'] ?? 0);
if ($listingId <= 0) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'listing_id']);
    exit;
}

try {
    cx_bootstrap();
    $pdo = \App\Helpers\Database::pdo();
    $stmt = $pdo->prepare('SELECT id, status, title FROM trade_listings WHERE id = ? LIMIT 1');
    $stmt->execute([$listingId]);
    $row = $stmt->fetch();
    if ($row === false) {
        http_response_code(404);
        echo json_encode(['ok' => false, 'error' => 'not_found']);
        exit;
    }

    $pdo->prepare('UPDATE trade_listings SET status = ?, updated_at = ? WHERE id = ?')
        ->execute(['CANCELLED', microtime(true), $listingId]);

    $tables = [
        'listing_favorites',
        'listing_price_drop_pending',
        'listing_price_history',
        'listing_views',
    ];
    foreach ($tables as $table) {
        try {
            $pdo->prepare("DELETE FROM {$table} WHERE listing_id = ?")->execute([$listingId]);
        } catch (Throwable) {
            // opsiyonel tablolar
        }
    }

    echo json_encode([
        'ok' => true,
        'listing_id' => $listingId,
        'title' => (string) ($row['title'] ?? ''),
        'status' => 'CANCELLED',
    ], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
}
