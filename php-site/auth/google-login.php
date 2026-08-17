<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/GoogleAuthService.php';

use App\Helpers\Security;
use App\Services\GoogleAuthService;

cx_bootstrap(false);

Security::rateLimit('google_login', 20, 60);

$state = bin2hex(random_bytes(16));
$_SESSION['google_oauth_state'] = $state;
$next = cx_safe_next((string) ($_GET['next'] ?? '/index.php'));
$_SESSION['google_oauth_next'] = $next;
$_SESSION['google_oauth_country'] = cx_normalize_country((string) ($_GET['country'] ?? 'tr'));

$url = GoogleAuthService::authUrl($state);
if ($url === null) {
    cx_flash('error', 'Google girisi yapilandirilmamis. config/google.local.php dosyasini doldurun.');
    cx_redirect('/login.php');
}
header('Location: ' . $url);
exit;
