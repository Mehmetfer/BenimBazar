<?php

/**
 * GET /api/v1/listings/detail?id=<id>
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;
use App\Helpers\Database;

api_method('GET');

$id = (int) ($_GET['id'] ?? 0);
if ($id <= 0) {
    api_error('Gecersiz ilan ID.', 422, 'INVALID_ID');
}

$token    = Auth::tokenFromRequest();
$viewer   = $token ? Auth::userFromToken($token) : null;
$viewerId = $viewer ? (int) $viewer['id'] : null;

$pdo  = Database::pdo();
$stmt = $pdo->prepare(
    'SELECT l.*, u.username AS owner_username, u.phone AS owner_phone, u.city AS owner_city
     FROM trade_listings l
     JOIN users u ON u.id = l.owner_id
     WHERE l.id = ?
     LIMIT 1'
);
$stmt->execute([$id]);
$l = $stmt->fetch();

if (!$l) {
    api_error('İlan bulunamadı.', 404, 'NOT_FOUND');
}

// Görüntülenme sayacı artır
try {
    $pdo->prepare('UPDATE trade_listings SET view_count = COALESCE(view_count,0)+1 WHERE id = ?')
        ->execute([$id]);
} catch (Throwable) {}

$baseUrl = rtrim((string) (cx_app_config()['url'] ?? ''), '/');

$photos = [];
if (!empty($l['photos'])) {
    $raw = is_string($l['photos']) ? json_decode($l['photos'], true) : $l['photos'];
    if (is_array($raw)) {
        foreach ($raw as $p) {
            $photos[] = $baseUrl . '/uploads/' . $p;
        }
    }
}

// Favoride mi?
$isFav = false;
if ($viewerId !== null) {
    $fStmt = $pdo->prepare('SELECT 1 FROM favorites WHERE user_id = ? AND listing_id = ? LIMIT 1');
    $fStmt->execute([$viewerId, $id]);
    $isFav = (bool) $fStmt->fetch();
}

// Karakteristikler
$attrs = [];
if (!empty($l['attributes'])) {
    $raw = is_string($l['attributes']) ? json_decode($l['attributes'], true) : $l['attributes'];
    if (is_array($raw)) {
        $attrs = $raw;
    }
}

api_ok([
    'id'          => (int) $l['id'],
    'no'          => cx_listing_no((int) $l['id']),
    'title'       => $l['title'] ?? '',
    'description' => $l['description'] ?? '',
    'price'       => $l['price'] !== null ? (float) $l['price'] : null,
    'currency'    => $l['currency'] ?? 'TRY',
    'status'      => $l['status'] ?? 'active',
    'category'    => $l['category'] ?? '',
    'city'        => $l['city'] ?? '',
    'country'     => $l['country'] ?? 'tr',
    'photos'      => $photos,
    'thumb'       => $photos[0] ?? null,
    'attributes'  => $attrs,
    'view_count'  => (int) ($l['view_count'] ?? 0),
    'is_favorite' => $isFav,
    'owner'       => [
        'id'       => (int) ($l['owner_id'] ?? 0),
        'username' => $l['owner_username'] ?? '',
        'city'     => $l['owner_city'] ?? '',
        // Telefon sadece giriş yapmış kullanıcıya
        'phone'    => $viewerId !== null ? ($l['owner_phone'] ?? null) : null,
    ],
    'created_at'  => $l['created_at'] ?? null,
    'url'         => $baseUrl . '/listing.php?id=' . (int) $l['id'],
]);
