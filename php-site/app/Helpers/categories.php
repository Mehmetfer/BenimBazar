<?php
declare(strict_types=1);

/**
 * Tek kaynak: ana sayfa chip/ikon + ilan verme formu.
 * Yalnizca 5 arac kategorisi.
 *
 * @return list<array{slug:string,label:string,parent:string,veh:string,icon:string,in_chips:bool,in_grid:bool}>
 */
function cx_marketplace_catalog(): array
{
    return [
        ['slug' => 'otomobil', 'label' => 'Otomobil', 'parent' => 'Araçlar', 'veh' => 'otomobil', 'icon' => '🚗', 'in_chips' => true, 'in_grid' => true],
        ['slug' => 'motosiklet', 'label' => 'Motosiklet', 'parent' => 'Araçlar', 'veh' => 'motosiklet', 'icon' => '🏍️', 'in_chips' => true, 'in_grid' => true],
        ['slug' => 'bisiklet', 'label' => 'Bisiklet', 'parent' => 'Araçlar', 'veh' => 'bisiklet', 'icon' => '🚲', 'in_chips' => true, 'in_grid' => true],
        ['slug' => 'ticari-arac', 'label' => 'Ticari Araç', 'parent' => 'Araçlar', 'veh' => 'ticari', 'icon' => '🚚', 'in_chips' => true, 'in_grid' => true],
        ['slug' => 'antika-arac', 'label' => 'Antika Araç', 'parent' => 'Araçlar', 'veh' => 'antika-arac', 'icon' => '🏛️', 'in_chips' => true, 'in_grid' => true],
    ];
}

/** @return array{slug:string,label:string,parent:string,veh:string,icon:string,in_chips:bool,in_grid:bool}|null */
function cx_marketplace_by_slug(string $slug): ?array
{
    $slug = trim($slug);
    foreach (cx_marketplace_catalog() as $row) {
        if ($row['slug'] === $slug) {
            return $row;
        }
    }
    return null;
}

/** @return array{slug:string,label:string,parent:string,veh:string,icon:string,in_chips:bool,in_grid:bool}|null */
function cx_marketplace_by_label(string $label): ?array
{
    $label = trim($label);
    foreach (cx_marketplace_catalog() as $row) {
        if ($row['label'] === $label) {
            return $row;
        }
    }
    return null;
}

/** @return list<string> */
function cx_marketplace_parents(): array
{
    return ['Araçlar'];
}

/** Ilan formu — ust gruba gore optgroup. @return array<string, list<array{slug:string,label:string}>> */
function cx_listing_category_groups(): array
{
    $groups = [];
    foreach (cx_marketplace_catalog() as $row) {
        $groups[$row['parent']][] = ['slug' => $row['slug'], 'label' => $row['label']];
    }
    return $groups;
}

/**
 * Slug veya arac segmentinden DB alanlari.
 *
 * @return array{category:string,subcategory:string,slug:string,veh:string}|null
 */
function cx_resolve_listing_category(?string $slug, ?string $vehSegment = null): ?array
{
    if ($vehSegment !== null && $vehSegment !== '') {
        foreach (cx_marketplace_catalog() as $row) {
            if ($row['veh'] === $vehSegment) {
                return [
                    'category' => $row['parent'],
                    'subcategory' => $row['label'],
                    'slug' => $row['slug'],
                    'veh' => $row['veh'],
                ];
            }
        }
    }
    if ($slug !== null && $slug !== '') {
        $row = cx_marketplace_by_slug($slug);
        if ($row !== null) {
            return [
                'category' => $row['parent'],
                'subcategory' => $row['label'],
                'slug' => $row['slug'],
                'veh' => $row['veh'],
            ];
        }
    }
    return null;
}

/** Ana sayfa / filtre meta + tek ust grup */
function cx_categories(): array
{
    return array_merge(
        ['TÜM TAKASLAR', 'POPÜLER', 'YENİ', 'YAKININDA', 'HIZLI TAKAS'],
        cx_marketplace_parents()
    );
}

function cx_meta_category(string $cat): bool
{
    return in_array($cat, ['TÜM TAKASLAR', 'POPÜLER', 'YENİ', 'YAKININDA', 'HIZLI TAKAS'], true);
}

/** Ana sayfa chip satiri */
function cx_home_chips(): array
{
    $out = [];
    foreach (cx_marketplace_catalog() as $row) {
        if (empty($row['in_chips'])) {
            continue;
        }
        $out[] = [
            'slug' => $row['slug'],
            'label' => $row['label'],
            'cat' => $row['parent'],
            'veh' => $row['veh'],
        ];
    }
    return $out;
}

/** Ana sayfa ikon grid */
function cx_home_icon_categories(): array
{
    $out = [];
    foreach (cx_marketplace_catalog() as $row) {
        if (empty($row['in_grid'])) {
            continue;
        }
        $out[] = [
            'slug' => $row['slug'],
            'label' => $row['label'],
            'icon' => $row['icon'],
            'cat' => $row['parent'],
            'veh' => $row['veh'],
        ];
    }
    return $out;
}

function cx_home_category_href(
    string $q = '',
    ?string $subcatSlug = null,
    ?string $veh = null,
    ?string $parentFallback = null
): string {
    if ($veh === null && $subcatSlug !== null && $subcatSlug !== '') {
        $row = cx_marketplace_by_slug($subcatSlug);
        if ($row !== null) {
            $veh = $row['veh'];
        }
    }
    $params = array_filter([
        'veh' => $veh,
        'q' => $q !== '' ? $q : null,
    ], static fn ($v) => $v !== null && $v !== '');
    return '/index.php' . ($params !== [] ? '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986) : '');
}

function cx_home_filter_label(?string $subcatSlug, ?string $veh, string $cat): string
{
    if ($veh !== null && $veh !== '' && cx_vehicle_browse_active($veh)) {
        return cx_vehicle_segment_label($veh);
    }
    if ($subcatSlug !== null && $subcatSlug !== '') {
        $row = cx_marketplace_by_slug($subcatSlug);
        if ($row !== null) {
            return $row['label'];
        }
    }
    if ($cat !== 'TÜM TAKASLAR' && !cx_meta_category($cat)) {
        return $cat;
    }
    return '';
}

function cx_home_filter_active(
    array $item,
    string $subcat,
    string $veh,
    string $cat
): bool {
    $itemVeh = $item['veh'] ?? null;
    if ($itemVeh !== null) {
        return $veh === $itemVeh;
    }
    return false;
}
