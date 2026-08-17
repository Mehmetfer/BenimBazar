<?php
/**
 * Tek seferlik: users.country / phone / city kolonlarini ekler.
 * Ac: /migrate-user-columns.php?secret=DEPLOY_SECRET
 * Is bitince bu dosyayi silin.
 */
declare(strict_types=1);

header('Content-Type: text/plain; charset=utf-8');

require __DIR__ . '/bootstrap.php';

use App\Helpers\Database;
use App\Services\ListingSchemaService;

cx_bootstrap();

$cfgPath = __DIR__ . '/config/deploy.local.php';
$secret = (string) ($_GET['secret'] ?? $_POST['secret'] ?? '');
$ok = false;
if (is_file($cfgPath)) {
    /** @var array<string,mixed> $dc */
    $dc = require $cfgPath;
    $ok = hash_equals((string) ($dc['secret'] ?? ''), $secret);
}
if (!$ok) {
    $user = cx_current_user();
    $ok = $user !== null && cx_is_superadmin($user);
}
if (!$ok) {
    http_response_code(403);
    echo "Yetkisiz.\n";
    exit;
}

try {
    ListingSchemaService::ensureUserColumns();
    $pdo = Database::pdo();
    foreach (['country', 'phone', 'city'] as $col) {
        $safe = preg_replace('/[^a-zA-Z0-9_]/', '', $col) ?? '';
        $st = $pdo->query('SHOW COLUMNS FROM users LIKE ' . $pdo->quote($safe));
        $row = $st ? $st->fetch() : false;
        echo $col . ': ' . ($row ? 'OK ' . ($row['Type'] ?? '') : 'YOK') . "\n";
    }
    echo "TAMAM\n";
} catch (Throwable $e) {
    http_response_code(500);
    echo 'HATA: ' . $e->getMessage() . "\n";
}
