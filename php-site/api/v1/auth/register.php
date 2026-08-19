<?php

/**
 * POST /api/v1/auth/register
 *
 * Body: { username, password, email, phone, city, country }
 * Response: { ok: true, data: { token, expires_at, user: {...} } }
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;
use App\Helpers\Database;
use App\Helpers\Security;
use App\Services\ListingSchemaService;

api_method('POST');
Security::rateLimit('api_register', 5, 3600);

$body     = api_json_body();
$username = trim((string) ($body['username'] ?? ''));
$password = (string) ($body['password'] ?? '');
$email    = trim((string) ($body['email'] ?? ''));
$phone    = trim((string) ($body['phone'] ?? ''));
$city     = trim((string) ($body['city'] ?? ''));
$country  = cx_normalize_country((string) ($body['country'] ?? 'tr'));

$errors = [];
if (strlen($username) < 3) {
    $errors[] = 'Kullanici adi en az 3 karakter olmali.';
}
if (strlen($password) < 6) {
    $errors[] = 'Sifre en az 6 karakter olmali.';
}
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    $errors[] = 'Gecerli bir e-posta girin.';
}
$phoneDigits = preg_replace('/\D+/', '', $phone) ?? '';
if (strlen($phoneDigits) < 10) {
    $errors[] = 'Gecerli bir GSM numarasi girin.';
}
if ($city === '') {
    $errors[] = 'Sehir zorunlu.';
}
if (!in_array($country, ['kktc', 'tr'], true)) {
    $errors[] = 'Ulke geçersiz (kktc veya tr).';
}

if ($errors !== []) {
    api_error(implode(' ', $errors), 422, 'VALIDATION_ERROR');
}

try {
    ListingSchemaService::ensureUserColumns();
} catch (Throwable) {
    // ignore — kolon zaten varsa sorun yok
}

$pdo = Database::pdo();
$dup = $pdo->prepare('SELECT id FROM users WHERE username = ? OR email = ? LIMIT 1');
$dup->execute([$username, $email]);
if ($dup->fetch()) {
    api_error('Bu kullanici adi veya e-posta zaten kayitli.', 409, 'ALREADY_EXISTS');
}

$hash = Auth::hashPassword($password);
$now  = microtime(true);

$pdo->prepare(
    'INSERT INTO users (username, password_hash, role, country, email, phone, city, created_at)
     VALUES (?,?,?,?,?,?,?,?)'
)->execute([$username, $hash, 'user', $country, $email, $phone, $city, $now]);

$uid = (int) $pdo->lastInsertId();

$days      = 90;
$token     = Auth::newSession($uid, $days);
$expiresAt = time() + ($days * 86400);

api_ok([
    'token'      => $token,
    'expires_at' => $expiresAt,
    'user'       => [
        'id'       => $uid,
        'username' => $username,
        'role'     => 'user',
        'country'  => $country,
        'score'    => 0,
    ],
], 201);
