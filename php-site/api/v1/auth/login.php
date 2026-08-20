<?php

/**
 * POST /api/v1/auth/login
 *
 * Body: { "username": "...", "password": "..." }
 *   veya { "email": "...", "password": "..." }
 *
 * Response: { ok: true, data: { token, expires_at, user: {...} } }
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;
use App\Helpers\Database;
use App\Helpers\Security;

api_method('POST');
Security::rateLimit('api_login', 10, 300); // 10 deneme / 5 dakika

$body   = api_json_body();
$ident  = trim((string) ($body['username'] ?? $body['email'] ?? ''));
$pass   = (string) ($body['password'] ?? '');

if ($ident === '' || $pass === '') {
    api_error('Kullanici adi/e-posta ve şifre gerekli.', 422, 'MISSING_FIELDS');
}

$pdo  = Database::pdo();
$stmt = $pdo->prepare(
    'SELECT id, username, password_hash, role, suspended, country,
            change_score, vip_starts_at, vip_ends_at
     FROM users
     WHERE username = ? OR email = ?
     LIMIT 1'
);
$stmt->execute([$ident, $ident]);
$user = $stmt->fetch();

if (!$user || !Auth::verifyPassword($pass, (string) ($user['password_hash'] ?? ''))) {
    api_error('Kullanici adi veya şifre hatalı.', 401, 'INVALID_CREDENTIALS');
}

if ((int) ($user['suspended'] ?? 0) === 1) {
    api_error('Hesap askıya alınmış.', 403, 'SUSPENDED');
}

$days      = 90; // Mobil için daha uzun oturum
$token     = Auth::newSession((int) $user['id'], $days);
$expiresAt = time() + ($days * 86400);

api_ok([
    'token'      => $token,
    'expires_at' => $expiresAt,
    'user'       => [
        'id'       => (int) $user['id'],
        'username' => $user['username'],
        'role'     => $user['role'],
        'country'  => cx_normalize_country((string) ($user['country'] ?? 'tr')),
        'score'    => (int) ($user['change_score'] ?? 0),
    ],
]);
