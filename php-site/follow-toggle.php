<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SocialService.php';

use App\Helpers\Security;
use App\Services\SocialService;

cx_bootstrap();
$user = cx_require_user();
Security::requireCsrf();

$followingId = (int) ($_POST['user_id'] ?? 0);
$back = cx_safe_next((string) ($_POST['back'] ?? '/index.php'));
if ($followingId <= 0) {
    cx_redirect($back);
}

SocialService::toggleFollow((int) $user['id'], $followingId);
cx_redirect($back);
