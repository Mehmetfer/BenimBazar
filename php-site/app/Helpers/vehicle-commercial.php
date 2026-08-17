<?php
declare(strict_types=1);

use App\Services\ListingService;

/** Car.gr tarzı ticari araç alt türleri. */
function cx_vehicle_commercial_types(): array
{
    return [
        'kamyonet' => [
            'label' => "Kamyonet (7,5 t'ye kadar)",
            'short' => 'Kamyonet',
            'icon' => 'van',
        ],
        'kamyon' => [
            'label' => "Kamyon (7,5 t üzeri)",
            'short' => 'Kamyon',
            'icon' => 'truck',
        ],
        'tarim' => [
            'label' => 'Tarım',
            'short' => 'Tarım',
            'icon' => 'tractor',
        ],
        'is-makinesi' => [
            'label' => 'İş makinesi',
            'short' => 'İş makinesi',
            'icon' => 'excavator',
        ],
        'cekici' => [
            'label' => 'Çekici',
            'short' => 'Çekici',
            'icon' => 'tractor-unit',
        ],
        'dorse' => [
            'label' => 'Dorse / Yarı römork',
            'short' => 'Dorse',
            'icon' => 'semi-trailer',
        ],
        'otobus' => [
            'label' => 'Otobüs / Minibüs',
            'short' => 'Otobüs',
            'icon' => 'bus',
        ],
        'forklift' => [
            'label' => 'Forklift',
            'short' => 'Forklift',
            'icon' => 'forklift',
        ],
        'romork' => [
            'label' => 'Römork',
            'short' => 'Römork',
            'icon' => 'trailer',
        ],
        'taksi' => [
            'label' => 'Taksi',
            'short' => 'Taksi',
            'icon' => 'taxi',
        ],
    ];
}

function cx_vehicle_commercial_type_valid(?string $id): bool
{
    $id = trim((string) $id);
    return $id !== '' && isset(cx_vehicle_commercial_types()[$id]);
}

function cx_vehicle_commercial_type_label(?string $id): string
{
    $id = trim((string) $id);
    return cx_vehicle_commercial_types()[$id]['label'] ?? '';
}

function cx_vehicle_commercial_type_short(?string $id): string
{
    $id = trim((string) $id);
    return cx_vehicle_commercial_types()[$id]['short'] ?? '';
}

/** @param array<string,mixed> $filters */
function cx_vehicle_commercial_type_href(string $typeId, string $q = '', array $filters = []): string
{
    $merged = $filters;
    unset($merged['make'], $merged['model'], $merged['commercial_type']);
    $merged['commercial_type'] = $typeId;
    return cx_vehicle_filter_href('ticari', $q, $merged);
}

/** @return array<string,int> */
function cx_vehicle_commercial_type_counts(): array
{
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }

    $svc = new ListingService();
    $cache = $svc->vehicleCommercialTypeCounts();
    return $cache;
}

/** @param array<string,mixed> $item */
function cx_listing_commercial_type(array $item): string
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $stored = trim((string) ($vehicle['commercial_type'] ?? ''));
    if (cx_vehicle_commercial_type_valid($stored)) {
        return $stored;
    }

    $hay = mb_strtolower(
        (string) ($item['title'] ?? '') . ' ' . (string) ($item['description'] ?? '') . ' ' . (string) ($vehicle['body'] ?? ''),
        'UTF-8'
    );

    $rules = [
        'taksi' => ['taksi', 'taxi'],
        'forklift' => ['forklift', 'istif'],
        'otobus' => ['otobüs', 'otobus', 'minibüs', 'minibus', 'midibus'],
        'dorse' => ['dorse', 'yarı römork', 'semi trailer', 'treyler'],
        'romork' => ['römork', 'romork', 'treiler'],
        'cekici' => ['çekici', 'cekici', 'tır', ' tir '],
        'is-makinesi' => ['iş makinesi', 'is makinesi', 'ekskavatör', 'kepçe', 'loader', 'buldozer'],
        'tarim' => ['traktör', 'traktor', 'tarım', 'biçerdöver', 'pulluk'],
        'kamyon' => ['kamyon', 'isuzu n', 'n-series', '7.5 t üzeri', 'ağır'],
        'kamyonet' => ['panelvan', 'transit', 'sprinter', 'ducato', 'crafter', 'kamyonet', 'pick-up', 'pickup', 'van'],
    ];

    foreach ($rules as $type => $keywords) {
        foreach ($keywords as $kw) {
            if (str_contains($hay, $kw)) {
                return $type;
            }
        }
    }

    return 'kamyonet';
}

function cx_vehicle_commercial_type_icon_svg(string $icon): string
{
    $paths = [
        'van' => '<path d="M4 14h26v8H4zM8 14V9h12v5M24 14V11h6v3M10 22a2 2 0 1 0 .01 0M24 22a2 2 0 1 0 .01 0"/>',
        'truck' => '<path d="M3 15h18v7H3zM21 15h6l3 4v3h-9V15zM8 22a2 2 0 1 0 .01 0M26 22a2 2 0 1 0 .01 0M21 12V8H6V15"/>',
        'tractor' => '<path d="M8 24a3 3 0 1 0 .01 0M22 24a4 4 0 1 0 .01 0M10 18h8M6 18l2-8h10l2 8M18 10V6h6v4"/>',
        'excavator' => '<path d="M6 24h16M8 20l-2-6h6l2 6M14 14l10-6-2 4-8 2M20 8l4-2"/>',
        'tractor-unit' => '<path d="M6 22a3 3 0 1 0 .01 0M24 22a4 4 0 1 0 .01 0M8 18h10M6 18l2-7h8l2 7M18 11h8v7h-8z"/>',
        'semi-trailer' => '<path d="M4 16h22v6H4zM26 18h4v4h-4zM8 22a2 2 0 1 0 .01 0M24 22a2 2 0 1 0 .01 0"/>',
        'bus' => '<path d="M5 10h22a3 3 0 0 1 3 3v9H5V10zM8 22a2 2 0 1 0 .01 0M24 22a2 2 0 1 0 .01 0M8 14h16M8 18h12"/>',
        'forklift' => '<path d="M10 24a2 2 0 1 0 .01 0M8 20V8h4v12M12 12h8v4H12zM20 8v12M20 8h4v6h-4"/>',
        'trailer' => '<path d="M4 16h20v6H4zM24 17h4v4h-4zM8 22a2 2 0 1 0 .01 0M22 22a2 2 0 1 0 .01 0"/>',
        'taxi' => '<path d="M6 14h20v8H6zM10 22a2 2 0 1 0 .01 0M22 22a2 2 0 1 0 .01 0M12 14V10h8v4M14 10h4l1-3h-6z"/>',
    ];
    $d = $paths[$icon] ?? $paths['van'];
    return '<svg class="vehicle-commercial-type__icon" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        . '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        . $d
        . '</g></svg>';
}
