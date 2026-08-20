<?php

declare(strict_types=1);

/**
 * Benzer araç ilanı tespiti (yumuşak): segment + marka + model + yıl + km toleransı.
 */

/**
 * @param array<string,mixed> $attrs
 * @return array{segment:string,make:string,model:string,year:int,km:int}|null
 */
function cx_listing_similar_fingerprint(array $attrs): ?array
{
    $segment = trim((string) ($attrs['segment'] ?? ''));
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = trim((string) ($vehicle['make'] ?? ''));
    $model = trim((string) ($vehicle['model'] ?? ''));
    $year = isset($vehicle['year']) ? (int) $vehicle['year'] : 0;
    $km = isset($vehicle['km']) ? (int) $vehicle['km'] : -1;

    if ($segment === '' || $make === '' || $model === '' || $year < 1900 || $km < 0) {
        return null;
    }

    return [
        'segment' => $segment,
        'make' => $make,
        'model' => $model,
        'year' => $year,
        'km' => $km,
    ];
}

function cx_listing_similar_model_key(string $model): string
{
    $v = mb_strtolower(trim($model), 'UTF-8');
    $v = str_replace(['-', '_', '.'], ' ', $v);
    $v = preg_replace('/\s+/u', ' ', $v) ?? $v;

    return trim($v);
}

function cx_listing_similar_km_tolerance(int $km): int
{
    return max(3000, (int) round($km * 0.05));
}

/** @return array{enabled:bool,limit:int} */
function cx_similar_listings_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['similar_listings'] ?? null) ? $app['similar_listings'] : [];

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'limit' => max(1, min(12, (int) ($cfg['limit'] ?? 6))),
    ];
}

function cx_similar_listings_enabled(): bool
{
    return cx_similar_listings_settings()['enabled'];
}

/**
 * @param array<string,mixed> $attrs
 */
function cx_listing_similar_context_label(array $attrs): string
{
    $fp = cx_listing_similar_fingerprint($attrs);
    $make = '';
    $model = '';
    $year = 0;
    $km = -1;

    if ($fp !== null) {
        $make = $fp['make'];
        $model = $fp['model'];
        $year = $fp['year'];
        $km = $fp['km'];
    } else {
        $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
        $make = trim((string) ($vehicle['make'] ?? ''));
        $model = trim((string) ($vehicle['model'] ?? ''));
        $year = (int) ($vehicle['year'] ?? 0);
        $km = (int) ($vehicle['km'] ?? -1);
    }

    $series = cx_listing_similar_title_series(['title' => $attrs['_title'] ?? '']);
    if ($series !== '' && !str_contains(mb_strtolower($model, 'UTF-8'), str_replace(' serisi', '', $series))) {
        $model = $series;
    }

    $parts = array_filter([
        $make,
        $model,
        $year >= 1900 ? (string) $year : '',
        $km >= 0 ? number_format($km, 0, ',', '.') . ' km' : '',
    ], static fn ($v) => trim((string) $v) !== '');

    return implode(' · ', $parts);
}

/**
 * @param array<string,mixed> $attrs
 * @return list<array<string,mixed>>
 */
function cx_listing_find_similar(
    array $attrs,
    int $excludeId = 0,
    int $limit = 8,
    int $preferOtherThanOwnerId = 0,
    string $scope = 'moderation'
): array {
    $fp = cx_listing_similar_fingerprint($attrs);
    if ($fp === null) {
        return [];
    }

    $limit = max(1, min(20, $limit));
    $segment = $fp['segment'];
    $make = cx_vehicle_canonical_make($fp['make'], $segment);
    $modelKey = cx_listing_similar_model_key($fp['model']);
    $year = $fp['year'];
    $km = $fp['km'];
    $tol = cx_listing_similar_km_tolerance($km);

    try {
        $pdo = \App\Helpers\Database::pdo();
    } catch (\Throwable) {
        return [];
    }

    $likeMake = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $make) . '%';
    $likeModel = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $fp['model']) . '%';

    $statusSql = $scope === 'public'
        ? "UPPER(COALESCE(l.status, '')) IN ('APPROVED', 'ACTIVE')"
        : "UPPER(COALESCE(l.status, '')) IN ('PENDING_MODERATION', 'PENDING', 'APPROVED', 'ACTIVE')";

    $sql = "SELECT l.id, l.owner_id, l.title, l.status, l.location, l.photo_urls, l.attrs_json,
                   l.category, l.subcategory, l.listing_mode, l.price_tl, l.created_at,
                   u.username AS owner_username
            FROM trade_listings l
            LEFT JOIN users u ON u.id = l.owner_id
            WHERE {$statusSql}
              AND l.attrs_json IS NOT NULL
              AND l.attrs_json <> ''
              AND l.attrs_json LIKE ?
              AND l.attrs_json LIKE ?";
    $params = [$likeMake, $likeModel];
    if ($excludeId > 0) {
        $sql .= ' AND l.id <> ?';
        $params[] = $excludeId;
    }
    $sql .= ' ORDER BY l.created_at DESC LIMIT 80';

    try {
        $stmt = $pdo->prepare($sql);
        $stmt->execute($params);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC) ?: [];
    } catch (\Throwable) {
        return [];
    }

    $matches = [];
    foreach ($rows as $row) {
        if (!is_array($row)) {
            continue;
        }
        $otherAttrs = cx_listing_attrs($row);
        $otherFp = cx_listing_similar_fingerprint($otherAttrs);
        if ($otherFp === null) {
            continue;
        }
        if ($otherFp['segment'] !== $segment) {
            continue;
        }
        if (!cx_vehicle_make_equals($make, $otherFp['make'], $segment)) {
            continue;
        }
        if (cx_listing_similar_model_key($otherFp['model']) !== $modelKey) {
            continue;
        }
        if ((int) $otherFp['year'] !== $year) {
            continue;
        }
        if (abs((int) $otherFp['km'] - $km) > $tol) {
            continue;
        }

        $photos = cx_photo_urls($row['photo_urls'] ?? '[]');
        $ownerId = (int) ($row['owner_id'] ?? 0);
        $matches[] = [
            'id' => (int) $row['id'],
            'listing_no' => cx_listing_no((int) $row['id']),
            'title' => (string) ($row['title'] ?? ''),
            'status' => (string) ($row['status'] ?? ''),
            'owner_id' => $ownerId,
            'owner_username' => (string) ($row['owner_username'] ?? '—'),
            'location' => (string) ($row['location'] ?? ''),
            'make' => $otherFp['make'],
            'model' => $otherFp['model'],
            'year' => $otherFp['year'],
            'km' => $otherFp['km'],
            'thumb' => $photos[0] ?? '',
            'admin_url' => '/admin/listing-edit.php?id=' . (int) $row['id'],
            'public_url' => '/listing.php?id=' . (int) $row['id'],
            'created_at' => (float) ($row['created_at'] ?? 0),
            'other_owner' => $preferOtherThanOwnerId > 0 && $ownerId !== $preferOtherThanOwnerId ? 0 : 1,
        ];
    }

    usort($matches, static function (array $a, array $b): int {
        return ($a['other_owner'] <=> $b['other_owner'])
            ?: ($b['created_at'] <=> $a['created_at']);
    });

    return array_slice($matches, 0, $limit);
}

/**
 * Detay sayfasi — skorlu benzer ilan (marka oncelikli, model/yil gevsek).
 *
 * @param array<string,mixed> $attrs
 * @return list<array<string,mixed>>
 */
function cx_listing_find_similar_public(array $attrs, int $excludeId = 0, int $limit = 6): array
{
    $base = cx_listing_similar_fingerprint($attrs);
    $segment = trim((string) ($attrs['segment'] ?? ''));
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = trim((string) ($vehicle['make'] ?? ''));

    if ($base !== null) {
        $segment = $base['segment'];
        $make = $base['make'];
    }

    if ($segment === '' || $make === '' || !isset(cx_vehicle_segments()[$segment])) {
        return [];
    }

    $make = cx_vehicle_canonical_make($make, $segment);
    $modelKey = cx_listing_similar_model_key((string) ($vehicle['model'] ?? ($base['model'] ?? '')));
    $year = (int) ($vehicle['year'] ?? ($base['year'] ?? 0));
    $km = (int) ($vehicle['km'] ?? ($base['km'] ?? -1));
    $titleSeries = cx_listing_similar_title_series(['title' => $attrs['_title'] ?? '']);

    $limit = max(1, min(12, $limit));

    try {
        $pdo = \App\Helpers\Database::pdo();
    } catch (\Throwable) {
        return [];
    }

    $likeMake = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $make) . '%';
    $likeSeg = '%"segment":"' . str_replace(['%', '_'], ['\\%', '\\_'], $segment) . '"%';

    $sql = "SELECT l.id, l.owner_id, l.title, l.status, l.location, l.photo_urls, l.attrs_json,
                   l.category, l.subcategory, l.listing_mode, l.price_tl, l.created_at,
                   u.username AS owner_username
            FROM trade_listings l
            LEFT JOIN users u ON u.id = l.owner_id
            WHERE UPPER(COALESCE(l.status, '')) IN ('APPROVED', 'ACTIVE')
              AND l.attrs_json IS NOT NULL AND l.attrs_json <> ''
              AND l.attrs_json LIKE ?
              AND l.attrs_json LIKE ?";
    $params = [$likeMake, $likeSeg];
    if ($excludeId > 0) {
        $sql .= ' AND l.id <> ?';
        $params[] = $excludeId;
    }
    $sql .= ' ORDER BY l.created_at DESC LIMIT 120';

    try {
        $stmt = $pdo->prepare($sql);
        $stmt->execute($params);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC) ?: [];
    } catch (\Throwable) {
        return [];
    }

    $scored = [];
    foreach ($rows as $row) {
        if (!is_array($row)) {
            continue;
        }
        $otherAttrs = cx_listing_attrs($row);
        $otherFp = cx_listing_similar_fingerprint($otherAttrs);
        if ($otherFp === null) {
            continue;
        }
        if ($otherFp['segment'] !== $segment) {
            continue;
        }
        if (!cx_vehicle_make_equals($make, $otherFp['make'], $segment)) {
            continue;
        }

        $score = 10;
        $otherModelKey = cx_listing_similar_model_key($otherFp['model']);
        if ($modelKey !== '' && $otherModelKey === $modelKey) {
            $score += 35;
        }

        $otherSeries = cx_listing_similar_title_series($row);
        if ($titleSeries !== '' && $otherSeries !== '' && $titleSeries === $otherSeries) {
            $score += 28;
        }

        if ($year >= 1900 && $otherFp['year'] >= 1900) {
            $yd = abs($year - (int) $otherFp['year']);
            if ($yd === 0) {
                $score += 18;
            } elseif ($yd === 1) {
                $score += 12;
            } elseif ($yd <= 3) {
                $score += 6;
            }
        }

        if ($km >= 0 && $otherFp['km'] >= 0) {
            $tol = cx_listing_similar_km_tolerance(max($km, $otherFp['km'], 5000));
            if (abs($km - (int) $otherFp['km']) <= $tol) {
                $score += 8;
            }
        }

        $photos = cx_photo_urls($row['photo_urls'] ?? '[]');
        $ownerId = (int) ($row['owner_id'] ?? 0);
        $scored[] = [
            'score' => $score,
            'id' => (int) $row['id'],
            'listing_no' => cx_listing_no((int) $row['id']),
            'title' => (string) ($row['title'] ?? ''),
            'status' => (string) ($row['status'] ?? ''),
            'owner_id' => $ownerId,
            'owner_username' => (string) ($row['owner_username'] ?? '—'),
            'location' => (string) ($row['location'] ?? ''),
            'make' => $otherFp['make'],
            'model' => $otherFp['model'],
            'year' => $otherFp['year'],
            'km' => $otherFp['km'],
            'thumb' => $photos[0] ?? '',
            'admin_url' => '/admin/listing-edit.php?id=' . (int) $row['id'],
            'public_url' => '/listing.php?id=' . (int) $row['id'],
            'created_at' => (float) ($row['created_at'] ?? 0),
        ];
    }

    usort($scored, static function (array $a, array $b): int {
        return ($b['score'] <=> $a['score']) ?: ($b['created_at'] <=> $a['created_at']);
    });

    $out = [];
    foreach ($scored as $row) {
        unset($row['score']);
        $out[] = $row;
        if (count($out) >= $limit) {
            break;
        }
    }

    return $out;
}

/** @param array{title?:string} $row */
function cx_listing_similar_title_series(array $row): string
{
    $title = mb_strtolower(trim((string) ($row['title'] ?? '')), 'UTF-8');
    if ($title === '') {
        return '';
    }
    if (preg_match('/\b([a-z0-9]+)\s*serisi\b/u', $title, $m)) {
        return trim($m[1]) . ' serisi';
    }
    if (preg_match('/\bseries\s+([a-z0-9]+)\b/u', $title, $m)) {
        return trim($m[1]) . ' serisi';
    }

    return '';
}

/**
 * Pending listesi için hafif kontrol (en fazla 1 aday).
 *
 * @param array<string,mixed> $attrs
 */
function cx_listing_has_similar(array $attrs, int $excludeId = 0): bool
{
    return cx_listing_find_similar($attrs, $excludeId, 1) !== [];
}
