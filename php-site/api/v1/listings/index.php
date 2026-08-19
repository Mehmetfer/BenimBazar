<?php

/**
 * GET /api/v1/listings
 *
 * Query params:
 *   q          — arama terimi
 *   category   — kategori slug
 *   region     — tr | kktc | all
 *   sort       — new | price_asc | price_desc | popular
 *   page       — sayfa no (1-based, varsayılan 1)
 *   per_page   — sayfa başına ilan (1-100, varsayılan 20)
 *   include_sold — 1 | 0
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Auth;
use App\Services\ListingService;

api_method('GET');

$token  = Auth::tokenFromRequest();
$viewer = $token ? Auth::userFromToken($token) : null;
$viewerId = $viewer ? (int) $viewer['id'] : null;

$q           = trim((string) ($_GET['q'] ?? ''));
$category    = trim((string) ($_GET['category'] ?? ''));
$region      = trim((string) ($_GET['region'] ?? 'all'));
$sort        = trim((string) ($_GET['sort'] ?? 'new'));
$includeSold = ($_GET['include_sold'] ?? '0') === '1';
$page        = max(1, (int) ($_GET['page'] ?? 1));
$perPage     = min(100, max(1, (int) ($_GET['per_page'] ?? 20)));

$svc  = new ListingService();
$all  = $svc->publicFeed(
    q: $q !== '' ? $q : null,
    viewerId: $viewerId,
    category: $category !== '' ? $category : null,
    includeSold: $includeSold,
    region: $region,
    sort: $sort
);

$total   = count($all);
$pages   = (int) ceil($total / $perPage);
$offset  = ($page - 1) * $perPage;
$items   = array_slice($all, $offset, $perPage);

$baseUrl = rtrim((string) (cx_app_config()['url'] ?? ''), '/');

$result = array_map(static function (array $l) use ($baseUrl): array {
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
        'id'          => (int) $l['id'],
        'no'          => cx_listing_no((int) $l['id']),
        'title'       => $l['title'] ?? '',
        'price'       => $l['price'] !== null ? (float) $l['price'] : null,
        'currency'    => $l['currency'] ?? 'TRY',
        'status'      => $l['status'] ?? 'active',
        'category'    => $l['category'] ?? '',
        'city'        => $l['city'] ?? '',
        'country'     => $l['country'] ?? 'tr',
        'photos'      => $photos,
        'thumb'       => $photos[0] ?? null,
        'owner'       => [
            'id'       => (int) ($l['owner_id'] ?? 0),
            'username' => $l['owner_username'] ?? '',
        ],
        'created_at'  => $l['created_at'] ?? null,
        'url'         => $baseUrl . '/listing.php?id=' . (int) $l['id'],
    ];
}, $items);

api_ok([
    'items'    => $result,
    'total'    => $total,
    'page'     => $page,
    'per_page' => $perPage,
    'pages'    => $pages,
]);
