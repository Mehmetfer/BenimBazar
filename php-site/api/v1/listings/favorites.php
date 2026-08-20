<?php

/**
 * GET    /api/v1/listings/favorites       — kullanicinin favorileri
 * POST   /api/v1/listings/favorites?id=X  — favori ekle
 * DELETE /api/v1/listings/favorites?id=X  — favori kaldır
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Database;

api_method('GET', 'POST', 'DELETE');
$user   = api_require_auth();
$uid    = (int) $user['id'];
$method = strtoupper($_SERVER['REQUEST_METHOD']);
$pdo    = Database::pdo();

if ($method === 'GET') {
    $stmt = $pdo->prepare(
        'SELECT l.id, l.title, l.price, l.currency, l.status, l.photos, l.city, l.country, l.created_at,
                u.username AS owner_username
         FROM favorites f
         JOIN trade_listings l ON l.id = f.listing_id
         JOIN users u ON u.id = l.owner_id
         WHERE f.user_id = ?
         ORDER BY f.created_at DESC'
    );
    $stmt->execute([$uid]);
    $rows = $stmt->fetchAll();

    $baseUrl = rtrim((string) (cx_app_config()['url'] ?? ''), '/');
    $items   = array_map(static function (array $l) use ($baseUrl): array {
        $photos = [];
        if (!empty($l['photos'])) {
            $raw = is_string($l['photos']) ? json_decode($l['photos'], true) : $l['photos'];
            if (is_array($raw)) {
                foreach ($raw as $p) {
                    $photos[] = $baseUrl . '/uploads/' . $p;
                }
            }
        }
        return [
            'id'       => (int) $l['id'],
            'no'       => cx_listing_no((int) $l['id']),
            'title'    => $l['title'],
            'price'    => $l['price'] !== null ? (float) $l['price'] : null,
            'currency' => $l['currency'] ?? 'TRY',
            'status'   => $l['status'],
            'thumb'    => $photos[0] ?? null,
            'photos'   => $photos,
            'city'     => $l['city'],
            'country'  => $l['country'],
            'owner'    => ['username' => $l['owner_username']],
        ];
    }, $rows);

    api_ok(['items' => $items, 'total' => count($items)]);
}

// POST / DELETE — id gerekli
$id = (int) ($_GET['id'] ?? (api_json_body()['id'] ?? 0));
if ($id <= 0) {
    api_error('Gecersiz ilan ID.', 422, 'INVALID_ID');
}

if ($method === 'POST') {
    // İlan var mı?
    $chk = $pdo->prepare('SELECT id FROM trade_listings WHERE id = ? LIMIT 1');
    $chk->execute([$id]);
    if (!$chk->fetch()) {
        api_error('İlan bulunamadı.', 404, 'NOT_FOUND');
    }
    try {
        $pdo->prepare(
            'INSERT IGNORE INTO favorites (user_id, listing_id, created_at) VALUES (?, ?, ?)'
        )->execute([$uid, $id, microtime(true)]);
    } catch (Throwable $e) {
        api_error('Favori eklenemedi.', 500);
    }
    api_ok(['favorited' => true, 'listing_id' => $id]);
}

if ($method === 'DELETE') {
    $pdo->prepare('DELETE FROM favorites WHERE user_id = ? AND listing_id = ?')
        ->execute([$uid, $id]);
    api_ok(['favorited' => false, 'listing_id' => $id]);
}
