<?php

/**
 * GET   /api/v1/user/profile         — kendi profili
 * PATCH /api/v1/user/profile         — profil güncelle (city, phone, country)
 * POST  /api/v1/user/profile/password — şifre değiştir
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;
use App\Helpers\Database;

api_method('GET', 'PATCH', 'POST');
$user   = api_require_auth();
$uid    = (int) $user['id'];
$method = strtoupper($_SERVER['REQUEST_METHOD']);
$pdo    = Database::pdo();

if ($method === 'GET') {
    $stmt = $pdo->prepare(
        'SELECT id, username, email, phone, city, country, role, change_score, created_at
         FROM users WHERE id = ? LIMIT 1'
    );
    $stmt->execute([$uid]);
    $row = $stmt->fetch();
    if (!$row) {
        api_error('Kullanici bulunamadi.', 404);
    }
    api_ok([
        'id'           => (int) $row['id'],
        'username'     => $row['username'],
        'email'        => $row['email'],
        'phone'        => $row['phone'],
        'city'         => $row['city'],
        'country'      => cx_normalize_country((string) ($row['country'] ?? 'tr')),
        'role'         => $row['role'],
        'score'        => (int) ($row['change_score'] ?? 0),
        'created_at'   => $row['created_at'],
    ]);
}

if ($method === 'PATCH') {
    $body    = api_json_body();
    $allowed = ['city', 'phone', 'country'];
    $sets    = [];
    $args    = [];
    foreach ($allowed as $field) {
        if (array_key_exists($field, $body)) {
            $val = trim((string) $body[$field]);
            if ($field === 'country') {
                $val = cx_normalize_country($val);
                if (!in_array($val, ['tr', 'kktc'], true)) {
                    api_error('Gecersiz ulke degeri.', 422);
                }
            }
            $sets[] = "`{$field}` = ?";
            $args[] = $val;
        }
    }
    if ($sets === []) {
        api_error('Guncellenecek alan bulunamadi.', 422, 'NO_FIELDS');
    }
    $args[] = $uid;
    $pdo->prepare('UPDATE users SET ' . implode(', ', $sets) . ' WHERE id = ?')->execute($args);
    api_ok(['updated' => true]);
}

if ($method === 'POST') {
    // Şifre değiştir — ?action=password
    $body    = api_json_body();
    $current = (string) ($body['current_password'] ?? '');
    $new     = (string) ($body['new_password'] ?? '');

    if (strlen($new) < 6) {
        api_error('Yeni sifre en az 6 karakter olmali.', 422);
    }

    $stmt = $pdo->prepare('SELECT password_hash FROM users WHERE id = ? LIMIT 1');
    $stmt->execute([$uid]);
    $row = $stmt->fetch();
    if (!$row || !Auth::verifyPassword($current, (string) $row['password_hash'])) {
        api_error('Mevcut sifre yanlis.', 403, 'WRONG_PASSWORD');
    }

    $hash = Auth::hashPassword($new);
    $pdo->prepare('UPDATE users SET password_hash = ? WHERE id = ?')->execute([$hash, $uid]);

    // Diğer oturumları iptal et (mevcut token hariç değil — sadelik için hepsini bırak)
    api_ok(['updated' => true]);
}
