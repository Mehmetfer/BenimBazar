<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/PriceDropAlertService.php';
require_once __DIR__ . '/app/Services/SocialService.php';

use App\Helpers\Security;
use App\Services\PriceDropAlertService;
use App\Services\SocialService;

cx_bootstrap();

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    cx_flash('error', 'Gecersiz istek.');
    cx_redirect('/index.php');
}

Security::requireCsrf();
$user = cx_require_user();

if (!cx_price_drop_alerts_enabled()) {
    cx_flash('error', 'Akıllı bildirimler kapalı.');
    cx_redirect('/index.php');
}

$id = (int) ($_POST['id'] ?? 0);
$back = (string) ($_POST['back'] ?? '/');
if ($id <= 0) {
    cx_redirect('/');
}

try {
    if (!SocialService::isFavorited((int) $user['id'], $id)) {
        throw new RuntimeException('Once ilani favorilere ekleyin.');
    }
    $enabled = (new PriceDropAlertService())->toggleAlert((int) $user['id'], $id);
    cx_flash('ok', $enabled ? 'Akıllı bildirimler açıldı.' : 'Akıllı bildirimler kapatıldı.');
} catch (Throwable $e) {
    cx_flash('error', $e->getMessage());
}

cx_redirect(cx_safe_next($back !== '' ? $back : '/index.php'));
