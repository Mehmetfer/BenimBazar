<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingService.php';
require_once __DIR__ . '/app/Services/SocialService.php';

use App\Helpers\Security;
use App\Services\ListingService;
use App\Services\SocialService;

cx_bootstrap();

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    cx_flash('error', 'Gecersiz istek.');
    cx_redirect('/index.php');
}

Security::requireCsrf();
$user = cx_require_user();

$id = (int) ($_POST['id'] ?? 0);
$back = (string) ($_POST['back'] ?? '/');
if ($id <= 0) {
    cx_redirect('/');
}

try {
    SocialService::toggleFavorite((int) $user['id'], $id);
} catch (Throwable $e) {
    cx_flash('error', $e->getMessage());
}

cx_redirect(cx_safe_next($back !== '' ? $back : '/index.php'));
