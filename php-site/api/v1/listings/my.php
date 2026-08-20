<?php

/**
 * GET /api/v1/listings/my
 * Oturumdaki kullanicinin kendi ilanları.
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Database;

api_method('GET');
$user = api_require_auth();
$uid  = (int) $user['id'];

$pdo  = Database::pdo();
$stmt = $pdo->prepare(
    'SELECT id, title, price, currency, status, photos, city, country, view_count, created_at
     FROM trade_listings
     WHERE owner_id = ?
     ORDER BY created_at DESC'
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
        'id'         => (int) $l['id'],
        'no'         => cx_listing_no((int) $l['id']),
        'title'      => $l['title'],
        'price'      => $l['price'] !== null ? (float) $l['price'] : null,
        'currency'   => $l['currency'] ?? 'TRY',
        'status'     => $l['status'],
        'thumb'      => $photos[0] ?? null,
        'photos'     => $photos,
        'city'       => $l['city'],
        'country'    => $l['country'],
        'view_count' => (int) ($l['view_count'] ?? 0),
        'created_at' => $l['created_at'],
    ];
}, $rows);

api_ok(['items' => $items, 'total' => count($items)]);
