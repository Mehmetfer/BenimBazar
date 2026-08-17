<?php

declare(strict_types=1);

/**
 * Eski otomobil ilanlarına boş ekspertiz iskeleti ekler (parça uydurmaz).
 * Detay sayfası zaten otomobil segmentinde ekspertiz gösterir; bu script
 * attrs_json içine expertise kaydı yazar ki düzenlemede form dolu gelsin.
 *
 * Kullanım:
 *   GET  /admin/expertise-backfill.php?dry=1&secret=...
 *   GET  /admin/expertise-backfill.php?run=1&secret=...
 */

require dirname(__DIR__) . '/bootstrap.php';

use App\Helpers\Database;

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
}

if (!$authorized) {
    http_response_code(403);
    echo "Yetkisiz.\n";
    exit;
}

$dry = isset($_GET['dry']) || isset($_POST['dry']);
$run = isset($_GET['run']) || isset($_POST['run']);

$pdo = Database::pdo();
$rows = $pdo->query(
    "SELECT id, title, category, subcategory, attrs_json, status
     FROM trade_listings
     ORDER BY id ASC"
)->fetchAll(PDO::FETCH_ASSOC) ?: [];

$candidates = [];
$skippedHas = 0;
$skippedNotCar = 0;

foreach ($rows as $row) {
    if (!cx_listing_matches_vehicle_segment($row, 'otomobil')) {
        $skippedNotCar++;
        continue;
    }
    $ex = cx_listing_expertise($row);
    $parts = is_array($ex['parts'] ?? null) ? $ex['parts'] : [];
    $photos = is_array($ex['photos'] ?? null) ? $ex['photos'] : [];
    if ($parts !== [] || $photos !== []) {
        $skippedHas++;
        continue;
    }
    $candidates[] = $row;
}

echo "=== Otomobil ekspertiz backfill ===\n";
echo 'Toplam satir: ' . count($rows) . "\n";
echo 'Otomobil degil: ' . $skippedNotCar . "\n";
echo 'Zaten ekspertizli: ' . $skippedHas . "\n";
echo 'Aday (bos ekspertiz): ' . count($candidates) . "\n\n";

if (!$run && !$dry) {
    echo "Kullanim: ?dry=1 veya ?run=1 (+ secret / superadmin)\n";
    exit;
}

$updated = 0;
$upd = $pdo->prepare('UPDATE trade_listings SET attrs_json = ? WHERE id = ?');

foreach ($candidates as $row) {
    $attrs = cx_listing_attrs($row);
    $attrs['expertise'] = [
        'has_report' => true,
        'photos' => [],
        'parts' => [],
    ];

    $json = json_encode($attrs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($json === false) {
        echo 'JSON hata id=' . (int) $row['id'] . "\n";
        continue;
    }

    echo ($dry ? '[dry] ' : '') . 'id=' . (int) $row['id'] . ' · ' . mb_strimwidth((string) $row['title'], 0, 60, '…') . "\n";

    if (!$dry) {
        $upd->execute([$json, (int) $row['id']]);
    }
    $updated++;
}

echo "\n" . ($dry ? 'Dry-run aday: ' : 'Guncellenen: ') . $updated . "\n";
