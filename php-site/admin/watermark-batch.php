<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

require_once dirname(__DIR__) . '/app/Services/WatermarkBatchService.php';

use App\Helpers\Security;
use App\Services\WatermarkBatchService;

cx_bootstrap();

header('Content-Type: text/plain; charset=UTF-8');

$authorized = false;
$user = cx_current_user();
if ($user && cx_is_superadmin($user)) {
    $authorized = true;
}

if (!$authorized) {
    $secret = (string) ($_POST['secret'] ?? $_GET['secret'] ?? '');
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
    echo "Yetkisiz. Superadmin veya ?secret= deploy anahtari gerekli.\n";
    exit;
}

$dryRun = isset($_GET['dry']) || isset($_POST['dry']);
$offset = max(0, (int) ($_GET['offset'] ?? $_POST['offset'] ?? 0));
$limit = max(1, min(100, (int) ($_GET['limit'] ?? $_POST['limit'] ?? 25)));
$run = isset($_GET['run']) || isset($_POST['run']) || $_SERVER['REQUEST_METHOD'] === 'POST' || $dryRun;

if (isset($_GET['probe'])) {
    $cfg = \App\Services\PhotoWatermarkService::burnConfig();
    $gi = gd_info();
    echo json_encode([
        'gd' => [
            'webp' => !empty($gi['WebP Support']),
            'jpeg' => !empty($gi['JPEG Support']),
            'png' => !empty($gi['PNG Support']),
            'version' => $gi['GD Version'] ?? '',
        ],
        'logo' => $cfg['logo'],
        'logo_exists' => is_file($cfg['logo']),
        'burn_on_upload' => $cfg['burn_on_upload'],
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) . "\n";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
}

$stats = WatermarkBatchService::stats();

echo "=== BenimBazar filigran toplu islem ===\n";
echo 'GD: ' . ($stats['gd'] ? 'ok' : 'YOK') . "\n";
echo 'Upload filigran: ' . ($stats['burn_on_upload'] ? 'acik' : 'kapali') . "\n";
echo 'Yerel dosya (ilanlarda): ' . (int) $stats['local_files'] . "\n";
echo 'Yedeklenmis (_wm_backup): ' . (int) $stats['with_backup'] . "\n";
echo "Yedek klasoru: uploads/_wm_backup/ (web kapali)\n\n";

if (!$run) {
    echo "Kullanim:\n";
    echo "  GET  ?dry=1              — dry-run (dosya sayisi, ornek liste)\n";
    echo "  POST run=1&limit=25      — batch uygula (CSRF + superadmin oturumu)\n";
    echo "  GET  ?run=1&secret=...   — curl ile batch (deploy secret)\n";
    echo "  offset=25 limit=25       — sonraki parti\n\n";
    echo "Ornek dry-run: /admin/watermark-batch.php?dry=1\n";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && !isset($_POST['run']) && !isset($_GET['run'])) {
    $_POST['run'] = '1';
}

$result = WatermarkBatchService::run($offset, $limit, $dryRun);

echo ($dryRun ? 'DRY-RUN' : 'CALISTI') . " offset={$offset} limit={$limit}\n";
echo 'Toplam yerel: ' . (int) $result['total'] . "\n";
echo 'Bu parti: islenen=' . (int) $result['processed']
    . ' atlanan=' . (int) $result['skipped']
    . ' hata=' . (int) $result['failed'] . "\n";

if (!$dryRun) {
    echo 'Yedek alinan=' . (int) $result['backed_up']
        . ' orijinalden geri yuklenen=' . (int) $result['restored'] . "\n";
}

if ($result['samples'] !== []) {
    echo "Ornekler:\n";
    foreach ($result['samples'] as $s) {
        echo '  - ' . $s . "\n";
    }
}

if ($result['errors'] !== []) {
    echo "Hatalar:\n";
    foreach (array_slice($result['errors'], 0, 20) as $err) {
        echo '  ! ' . $err . "\n";
    }
}

if (!$result['done']) {
    $next = (int) $result['next_offset'];
    echo "\nDevam: ?run=1&offset={$next}&limit={$limit}\n";
    if (!$dryRun) {
        echo "(Ayni secret veya oturumla tekrar cagirin)\n";
    }
} else {
    echo "\nTamamlandi — tum yerel dosyalar islendi.\n";
}
