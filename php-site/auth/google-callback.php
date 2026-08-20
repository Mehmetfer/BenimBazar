<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/GoogleAuthService.php';

use App\Helpers\Auth;
use App\Helpers\Security;
use App\Services\GoogleAuthService;

cx_bootstrap();

Security::rateLimit('google_callback', 20, 60);

$state = (string) ($_GET['state'] ?? '');
$code = (string) ($_GET['code'] ?? '');
$expected = (string) ($_SESSION['google_oauth_state'] ?? '');
$next = cx_safe_next((string) ($_SESSION['google_oauth_next'] ?? '/index.php'));
unset($_SESSION['google_oauth_state'], $_SESSION['google_oauth_next']);

if ($state === '' || !hash_equals($expected, $state)) {
    cx_flash('error', 'Google oturum dogrulamasi basarisiz.');
    cx_redirect('/login.php');
}

if ($code === '') {
    cx_flash('error', 'Google girisi iptal edildi.');
    cx_redirect('/login.php');
}

try {
    $profile = GoogleAuthService::exchangeCode($code);
    if ($profile === null) {
        throw new RuntimeException('Google token alinamadi');
    }
    $uid = GoogleAuthService::loginOrRegister($profile);
    $token = Auth::newSession($uid);
    Auth::setTokenCookie($token);
    cx_flash('ok', 'Google ile giris basarili.');
    cx_redirect($next);
} catch (Throwable $e) {
    cx_flash('error', 'Google girisi: ' . $e->getMessage());
    cx_redirect('/login.php');
}
