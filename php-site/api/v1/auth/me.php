<?php

/**
 * GET /api/v1/auth/me
 * Mevcut oturumdaki kullanicinin profilini döner.
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Database;

api_method('GET');
$user = api_require_auth();

// E-posta ve GSM gibi ek alanlar
$pdo  = Database::pdo();
$stmt = $pdo->prepare('SELECT email, phone, city, created_at FROM users WHERE id = ? LIMIT 1');
$stmt->execute([(int) $user['id']]);
$extra = $stmt->fetch() ?: [];

api_ok([
    'id'         => (int) $user['id'],
    'username'   => $user['username'],
    'role'       => $user['role'],
    'country'    => $user['country'],
    'score'      => (int) ($user['change_score'] ?? 0),
    'email'      => $extra['email'] ?? null,
    'phone'      => $extra['phone'] ?? null,
    'city'       => $extra['city'] ?? null,
    'created_at' => $extra['created_at'] ?? null,
]);
