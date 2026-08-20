<?php

declare(strict_types=1);

/** @return array{enabled:bool,default:string} */
function cx_listing_sort_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['listing_sort'] ?? null) ? $app['listing_sort'] : [];

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'default' => (string) ($cfg['default'] ?? 'date_desc'),
    ];
}

function cx_listing_sort_enabled(): bool
{
    return cx_listing_sort_settings()['enabled'];
}

/** @return array<string,string> */
function cx_listing_sort_options(): array
{
    return [
        'price_desc' => 'Fiyata göre (Önce en yüksek)',
        'price_asc' => 'Fiyata göre (Önce en düşük)',
        'date_desc' => 'Tarihe göre (Önce en yeni ilan)',
        'date_asc' => 'Tarihe göre (Önce en eski ilan)',
        'km_asc' => "Km'ye göre (Önce en düşük)",
        'km_desc' => "Km'ye göre (Önce en yüksek)",
        'year_asc' => 'Modele göre (Eski)',
        'year_desc' => 'Modele göre (Yeni)',
        'address_asc' => 'Adrese göre (A-Z)',
        'address_desc' => 'Adrese göre (Z-A)',
    ];
}

function cx_listing_sort_normalize(string $sort): string
{
    if ($sort === 'new') {
        return 'date_desc';
    }

    return $sort;
}

function cx_listing_sort_is_default(string $sort): bool
{
    return cx_listing_sort_normalize($sort) === cx_listing_sort_normalize(cx_listing_sort_settings()['default']);
}

function cx_listing_sort_from_request(): string
{
    $cfg = cx_listing_sort_settings();
    if (!$cfg['enabled']) {
        return cx_listing_sort_normalize($cfg['default']);
    }

    $sort = trim((string) ($_GET['sort'] ?? $cfg['default']));
    $sort = cx_listing_sort_normalize($sort);
    $allowed = array_keys(cx_listing_sort_options());
    if (!in_array($sort, $allowed, true)) {
        $default = cx_listing_sort_normalize($cfg['default']);

        return in_array($default, $allowed, true) ? $default : 'date_desc';
    }

    return $sort;
}

function cx_listing_sort_needs_expanded_fetch(string $sort): bool
{
    if (!cx_listing_sort_enabled()) {
        return false;
    }

    return !cx_listing_sort_is_default($sort);
}

function cx_listing_sort_needs_php(string $sort): bool
{
    if (!cx_listing_sort_enabled()) {
        return false;
    }

    return cx_listing_sort_normalize($sort) !== 'date_desc';
}

function cx_listing_sort_href(string $sort): string
{
    $qs = $_GET;
    $sort = cx_listing_sort_normalize($sort);
    if (cx_listing_sort_is_default($sort)) {
        unset($qs['sort']);
    } else {
        $qs['sort'] = $sort;
    }

    return '/index.php?' . http_build_query($qs, '', '&', PHP_QUERY_RFC3986);
}

/** @param array<string,mixed> $item */
function cx_listing_sort_price_value(array $item): ?float
{
    $fx = cx_listing_price_currency($item);
    if ($fx !== null && $fx['amount'] > 0) {
        return $fx['amount'];
    }

    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE') {
        $price = (float) ($item['price_tl'] ?? 0);
        if ($price > 0) {
            return $price;
        }
    }

    return null;
}

/** @param array<string,mixed> $item */
function cx_listing_sort_km_value(array $item): ?int
{
    $attrs = cx_listing_attrs($item);
    $veh = $attrs['vehicle'] ?? null;
    if (!is_array($veh)) {
        return null;
    }

    $km = $veh['km'] ?? null;
    if ($km === null || $km === '') {
        return null;
    }

    $digits = preg_replace('/\D+/', '', (string) $km) ?? '';
    if ($digits === '') {
        return null;
    }

    return (int) $digits;
}

/** @param array<string,mixed> $item */
function cx_listing_sort_year_value(array $item): ?int
{
    $attrs = cx_listing_attrs($item);
    $veh = $attrs['vehicle'] ?? null;
    if (!is_array($veh)) {
        return null;
    }

    $year = (int) ($veh['year'] ?? 0);

    return $year >= 1900 ? $year : null;
}

/** @param array<string,mixed> $item */
function cx_listing_sort_created(array $item): int
{
    $created = $item['created_at'] ?? '';
    if (is_numeric($created)) {
        return (int) $created;
    }

    $ts = strtotime((string) $created);

    return $ts !== false ? $ts : 0;
}

/** @param array<string,mixed> $item */
function cx_listing_sort_address_key(array $item): string
{
    $loc = trim((string) ($item['location'] ?? ''));
    if ($loc === '') {
        return 'zzzz';
    }

    return mb_strtolower($loc, 'UTF-8');
}

/** @param array<string,mixed> $a @param array<string,mixed> $b */
function cx_listing_sort_address_compare_items(array $a, array $b): int
{
    return strcmp(cx_listing_sort_address_key($a), cx_listing_sort_address_key($b));
}

/**
 * @param float|int|null $a
 * @param float|int|null $b
 * @param bool $asc
 */
function cx_listing_sort_nullable($a, $b, bool $asc): int
{
    if ($a === null && $b === null) {
        return 0;
    }
    if ($a === null) {
        return 1;
    }
    if ($b === null) {
        return -1;
    }

    return $asc ? ($a <=> $b) : ($b <=> $a);
}

/**
 * @param list<array<string,mixed>> $items
 * @return list<array<string,mixed>>
 */
function cx_listing_sort_items(array $items, string $sort): array
{
    $sort = cx_listing_sort_normalize($sort);
    if ($sort === 'date_desc' || $items === []) {
        return $items;
    }

    usort($items, static function (array $a, array $b) use ($sort): int {
        if ($sort === 'price_asc' || $sort === 'price_desc') {
            return cx_listing_sort_nullable(
                cx_listing_sort_price_value($a),
                cx_listing_sort_price_value($b),
                $sort === 'price_asc'
            );
        }
        if ($sort === 'date_asc') {
            return cx_listing_sort_created($a) <=> cx_listing_sort_created($b);
        }
        if ($sort === 'km_asc' || $sort === 'km_desc') {
            return cx_listing_sort_nullable(
                cx_listing_sort_km_value($a),
                cx_listing_sort_km_value($b),
                $sort === 'km_asc'
            );
        }
        if ($sort === 'year_asc' || $sort === 'year_desc') {
            return cx_listing_sort_nullable(
                cx_listing_sort_year_value($a),
                cx_listing_sort_year_value($b),
                $sort === 'year_asc'
            );
        }
        if ($sort === 'address_asc') {
            return cx_listing_sort_address_compare_items($a, $b);
        }
        if ($sort === 'address_desc') {
            return cx_listing_sort_address_compare_items($b, $a);
        }

        return cx_listing_sort_created($b) <=> cx_listing_sort_created($a);
    });

    return $items;
}
