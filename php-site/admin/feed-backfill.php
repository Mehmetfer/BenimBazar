<?php

declare(strict_types=1);

/**
 * Eski arac ilanlarina feed icin gerekli alanlari ekler (attrs, foto, kategori).
 *
 * Kullanim:
 *   GET /admin/feed-backfill.php?dry=1&secret=...
 *   GET /admin/feed-backfill.php?run=1&secret=...
 */

require dirname(__DIR__) . '/bootstrap.php';

use App\Services\ListingFeedBackfillService;

cx_bootstrap();

header('Content-Type: text/plain; charset=UTF-8');

$authorized = false;
$user = cx_current_user();
if ($user && cx_is_superadmin($user)) {
    $authorized = true;
}

if (!$authorized) {
    $secret = (string) ($_GET['secret'] ?? $_POST['secret'] ?? '');
    $cfgPath = dirname(__DIR__) . '/config/deploy.local.php';
    if ($secret !== '' && is_file($cfgPath)) {
        /** @var array<string,mixed> $dc */
        $dc = require $cfgPath;
        if (hash_equals((string) ($dc['secret'] ?? ''), $secret)) {
            $authorized = true;
        }
    }
    if (!$authorized && $secret !== '') {
        $localCreds = dirname(__DIR__, 2) . '/scripts/ftp-credentials.local.json';
        if (is_file($localCreds)) {
            $raw = json_decode((string) file_get_contents($localCreds), true);
            if (is_array($raw) && hash_equals((string) ($raw['deploy_secret'] ?? ''), $secret)) {
                $authorized = true;
            }
        }
    }
}

if (!$authorized) {
    http_response_code(403);
    echo "Yetkisiz.\n";
    exit;
}

$dry = isset($_GET['dry']) || isset($_POST['dry']);
$run = isset($_GET['run']) || isset($_POST['run']);

if (!$run && !$dry) {
    echo "Kullanim: ?dry=1 veya ?run=1 (+ secret veya superadmin oturumu)\n";
    exit;
}

$svc = new ListingFeedBackfillService();
$result = $svc->run($dry);

echo "=== Feed kalite backfill (Asama 5) ===\n";
echo 'Mod: ' . ($dry ? 'DRY-RUN' : 'RUN') . "\n";
echo 'Taranan: ' . $result['scanned'] . "\n";
echo 'Guncellenecek aday: ' . $result['candidates'] . "\n";
echo ($dry ? 'Dry aday: ' : 'Guncellenen: ') . $result['updated'] . "\n";
echo 'Atlanan (arac disi): ' . $result['skipped_non_vehicle'] . "\n";
echo 'Atlanan (diger): ' . $result['skipped_other'] . "\n\n";

foreach ($result['details'] as $line) {
    echo $line . "\n";
}

echo "\nBitti.\n";
