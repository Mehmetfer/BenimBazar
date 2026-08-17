<?php
declare(strict_types=1);

use App\Services\ListingService;

/** @return list<string> */
function cx_vehicle_model_catalog(string $veh, string $make): array
{
    $make = cx_vehicle_canonical_make($make, $veh);
    static $catalog = null;
    if ($catalog === null) {
        $catalog = cx_vehicle_model_catalog_data();
    }

    return $catalog[$veh][$make] ?? [];
}

function cx_vehicle_brand_in_catalog(string $make, string $veh): bool
{
    $make = cx_vehicle_canonical_make($make, $veh);
    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        if ($brand['name'] === $make) {
            return true;
        }
    }

    return false;
}

function cx_vehicle_model_in_catalog(string $model, string $veh, string $make): bool
{
    $make = cx_vehicle_canonical_make($make, $veh);
    $model = trim($model);
    if ($model === '' || $model === 'Diğer') {
        return $make === 'Diğer';
    }
    if ($model === cx_vehicle_model_custom_option()) {
        return false;
    }
    foreach (cx_vehicle_model_catalog($veh, $make) as $name) {
        if (cx_vehicle_model_equals($model, $name)) {
            return true;
        }
    }

    return false;
}

function cx_vehicle_model_custom_option(): string
{
    return '__manual__';
}

function cx_vehicle_sanitize_custom_model(string $raw): string
{
    $raw = trim(preg_replace('/\s+/u', ' ', $raw) ?? '');

    return mb_strlen($raw) > 48 ? mb_substr($raw, 0, 48) : $raw;
}

function cx_vehicle_custom_model_valid(string $model): bool
{
    return trim($model) !== '';
}

/** @return array{model:string,error:?string} */
function cx_vehicle_resolve_model_from_post(array $post, string $segment, string $make): array
{
    $make = cx_vehicle_canonical_make($make, $segment);
    $selected = trim((string) ($post['vehicle_model'] ?? ''));
    $custom = cx_vehicle_sanitize_custom_model((string) ($post['vehicle_model_custom'] ?? ''));
    $manualOpt = cx_vehicle_model_custom_option();

    if ($selected === $manualOpt) {
        if ($custom === '') {
            return ['model' => '', 'error' => 'Model adini yazin.'];
        }

        return ['model' => $custom, 'error' => null];
    }

    if ($selected === '') {
        if ($custom !== '' && cx_vehicle_custom_model_valid($custom)) {
            return ['model' => $custom, 'error' => null];
        }

        return ['model' => '', 'error' => 'Model secin veya listede yoksa elle yazin.'];
    }

    if (cx_vehicle_model_in_catalog($selected, $segment, $make)) {
        return ['model' => cx_vehicle_canonical_model($selected, $segment, $make), 'error' => null];
    }

    if (cx_vehicle_custom_model_valid($selected)) {
        return ['model' => $selected, 'error' => null];
    }

    return ['model' => '', 'error' => 'Gecerli bir model secin veya listede yok — elle yazin.'];
}

function cx_vehicle_canonical_model(string $raw, string $veh, string $make): string
{
    $raw = trim($raw);
    foreach (cx_vehicle_model_catalog($veh, $make) as $name) {
        if (cx_vehicle_model_equals($raw, $name)) {
            return $name;
        }
    }

    return $raw;
}

/** @return array{brands:list<string>,models:array<string,list<string>>} */
function cx_vehicle_make_model_form_data(string $veh): array
{
    $brands = [];
    $models = [];
    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        $name = $brand['name'];
        $brands[] = $name;
        $list = cx_vehicle_model_catalog($veh, $name);
        $models[$name] = $list !== [] || $name === 'Diğer' ? $list : ['Diğer'];
    }

    return ['brands' => $brands, 'models' => $models];
}

/** @return array<string,array{brands:list<string>,models:array<string,list<string>>}> */
function cx_vehicle_make_model_form_map(): array
{
    $map = [];
    foreach (array_keys(cx_vehicle_segments()) as $veh) {
        $map[$veh] = cx_vehicle_make_model_form_data($veh);
    }

    return $map;
}

/**
 * @param array<string,mixed> $vehicle
 * @param array<string,mixed> $post
 */
function cx_vehicle_assign_make_model(array &$vehicle, string $segment, array $post): ?string
{
    $make = trim((string) ($post['vehicle_make'] ?? ''));
    $model = trim((string) ($post['vehicle_model'] ?? ''));

    if (!in_array($segment, ['otomobil', 'motosiklet', 'ticari', 'antika-arac', 'bisiklet'], true)) {
        return null;
    }

    if ($make === '') {
        return 'Marka seçin.';
    }
    if (!cx_vehicle_brand_in_catalog($make, $segment)) {
        return $segment === 'bisiklet'
            ? 'Geçerli bir bisiklet markası seçin.'
            : 'Geçerli bir marka seçin.';
    }
    $make = cx_vehicle_canonical_make($make, $segment);
    $vehicle['make'] = $make;

    $modelPack = cx_vehicle_resolve_model_from_post($post, $segment, $make);
    if ($modelPack['error'] !== null) {
        return $modelPack['error'];
    }
    if ($modelPack['model'] === '') {
        return 'Model secin veya listede yoksa elle yazin.';
    }
    $vehicle['model'] = $modelPack['model'];

    return null;
}

function cx_vehicle_normalize_model_token(string $value): string
{
    $v = mb_strtolower(trim($value), 'UTF-8');
    $v = str_replace(['-', '_'], ' ', $v);
    $v = preg_replace('/\s+/u', ' ', $v) ?? $v;
    return trim($v);
}

function cx_vehicle_model_equals(string $selected, string $listingModel): bool
{
    $a = cx_vehicle_normalize_model_token($selected);
    $b = cx_vehicle_normalize_model_token($listingModel);
    if ($a === '' || $b === '') {
        return false;
    }
    if ($a === $b) {
        return true;
    }
    return str_starts_with($b, $a) || str_starts_with($a, $b);
}

/** @param array<string,mixed> $item */
function cx_listing_vehicle_model(array $item, ?string $veh = null, ?string $make = null): string
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $stored = trim((string) ($vehicle['model'] ?? ''));
    if ($stored !== '') {
        return $stored;
    }

    if ($veh === null) {
        $veh = trim((string) ($attrs['segment'] ?? ''));
    }
    $title = trim((string) ($item['title'] ?? ''));
    if ($title === '' || $veh === '') {
        return '';
    }

    $listingMake = $make ?? cx_listing_vehicle_make($item, $veh);
    if ($listingMake !== '') {
        foreach (cx_vehicle_model_catalog($veh, $listingMake) as $modelName) {
            if (mb_stripos($title, $modelName, 0, 'UTF-8') !== false) {
                return $modelName;
            }
        }
    }

    if ($listingMake !== '' && str_starts_with(mb_strtolower($title, 'UTF-8'), mb_strtolower($listingMake, 'UTF-8'))) {
        $rest = trim(mb_substr($title, mb_strlen($listingMake, 'UTF-8'), null, 'UTF-8'));
        $rest = preg_replace('/^[\s\-–]+/u', '', $rest) ?? $rest;
        if (preg_match('/^([A-Za-z0-9][A-Za-z0-9\.\-\s]{1,40})/u', $rest, $m)) {
            return trim($m[1]);
        }
    }

    return '';
}

/** @return array<string,int> */
function cx_vehicle_model_counts(string $veh, string $make, ?string $commercialType = null): array
{
    static $cache = [];
    $make = cx_vehicle_canonical_make($make, $veh);
    $key = $veh . '|' . $make . '|' . (string) $commercialType;
    if (isset($cache[$key])) {
        return $cache[$key];
    }
    $svc = new ListingService();
    $cache[$key] = $svc->vehicleModelCounts($veh, $make, $commercialType);
    return $cache[$key];
}

/**
 * @param array<string,mixed> $filters
 * @return array{make:string,models:list<array{name:string,count:int}>,total:int}
 */
function cx_vehicle_model_picker_data(string $veh, array $filters): array
{
    $rawMake = $filters['make'] ?? [];
    if (!is_array($rawMake)) {
        $rawMake = $rawMake !== '' ? [(string) $rawMake] : [];
    }
    $make = $rawMake !== [] ? cx_vehicle_canonical_make((string) $rawMake[0], $veh) : '';
    $commercialType = ($veh === 'ticari' && !empty($filters['commercial_type']))
        ? (string) $filters['commercial_type']
        : null;

    $counts = $make !== '' ? cx_vehicle_model_counts($veh, $make, $commercialType) : [];
    $names = cx_vehicle_model_catalog($veh, $make);
    foreach (array_keys($counts) as $name) {
        if (!in_array($name, $names, true)) {
            $names[] = $name;
        }
    }

    $rows = [];
    $total = 0;
    foreach ($names as $name) {
        $count = (int) ($counts[$name] ?? 0);
        $total += $count;
        $rows[] = ['name' => $name, 'count' => $count];
    }

    usort($rows, static function (array $a, array $b): int {
        if ($a['count'] !== $b['count']) {
            return $b['count'] <=> $a['count'];
        }
        return strcasecmp($a['name'], $b['name']);
    });

    return ['make' => $make, 'models' => $rows, 'total' => $total];
}
