<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

require_once dirname(__DIR__) . '/app/Services/CelicaListingSeedService.php';

use App\Services\CelicaListingSeedService;

cx_bootstrap();

$authorized = false;
$user = cx_current_user();
if ($user && cx_is_staff($user)) {
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
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Yetkisiz. Superadmin girisi veya deploy secret gerekli.';
    exit;
}

$result = CelicaListingSeedService::seed(
    $user ? (int) ($user['id'] ?? 0) : null
);

$wantsJson = str_contains((string) ($_SERVER['HTTP_ACCEPT'] ?? ''), 'application/json')
    || (string) ($_GET['format'] ?? '') === 'json';

if ($wantsJson) {
    header('Content-Type: application/json; charset=UTF-8');
    echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

$title = 'Celica ilani';
$layout = 'admin';
$bodyClass = 'page-admin';
$adminTab = 'listings';
ob_start();
require dirname(__DIR__) . '/views/partials/admin-shell.php';
?>
<h1 class="admin-h1">Toyota Celica ilani</h1>
<?php foreach ($result['messages'] as $m): ?>
<p class="admin-lead"><?= cx_e($m) ?></p>
<?php endforeach; ?>
<?php if (!empty($result['listing_id'])): ?>
<p>
  <a class="admin-btn admin-btn--primary" href="<?= cx_e((string) $result['url']) ?>">Ilani gor</a>
  <a class="admin-btn" href="/admin/listing-edit.php?id=<?= (int) $result['listing_id'] ?>">Admin duzenle</a>
</p>
<?php endif; ?>
<?php
$content = ob_get_clean();
require dirname(__DIR__) . '/views/layout.php';
