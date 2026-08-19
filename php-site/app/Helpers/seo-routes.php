<?php

declare(strict_types=1);

require_once __DIR__ . '/kktc-locations.php';

/** @return array{enabled:bool,popular_brands_per_segment:int} */
function cx_seo_landing_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['seo_landing'] ?? null) ? $app['seo_landing'] : [];

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'popular_brands_per_segment' => max(5, min(30, (int) ($cfg['popular_brands_per_segment'] ?? 15))),
    ];
}

function cx_seo_landing_enabled(): bool
{
    return cx_seo_landing_settings()['enabled'];
}

function cx_seo_make_slug(string $make): string
{
    $token = cx_vehicle_normalize_make_token($make);

    return str_replace(' ', '-', $token);
}

function cx_seo_make_from_slug(string $slug, string $veh): ?string
{
    $slug = strtolower(trim($slug));
    if ($slug === '') {
        return null;
    }

    foreach (cx_vehicle_brand_catalog($veh) as $brand) {
        if (cx_seo_make_slug($brand['name']) === $slug) {
            return $brand['name'];
        }
        foreach ($brand['aliases'] ?? [] as $alias) {
            if (cx_seo_make_slug($alias) === $slug) {
                return $brand['name'];
            }
        }
    }

    $guess = cx_vehicle_canonical_make(str_replace('-', ' ', $slug), $veh);
    if ($guess !== '' && cx_seo_make_slug($guess) === $slug) {
        return $guess;
    }

    return null;
}

/**
 * @return array{type:string,region:string,city:string,veh:string,make:string}|null
 */
function cx_seo_route_parse(string $path): ?array
{
    $path = trim(strtolower($path), '/');
    if ($path === '') {
        return null;
    }

    $parts = array_values(array_filter(explode('/', $path), static fn (string $p): bool => $p !== ''));

    if ($parts === [] || $parts[0] !== 'kktc' && $parts[0] !== 'arac') {
        return null;
    }

    if ($parts[0] === 'kktc') {
        $route = [
            'type' => 'kktc',
            'region' => 'kktc',
            'city' => '',
            'veh' => '',
            'make' => '',
        ];
        $idx = 1;
        if (isset($parts[$idx]) && cx_kktc_city_valid($parts[$idx])) {
            $route['city'] = $parts[$idx];
            $idx++;
        }
        if (isset($parts[$idx])) {
            if (!cx_vehicle_browse_active($parts[$idx])) {
                return null;
            }
            $route['veh'] = $parts[$idx];
            $idx++;
            if (isset($parts[$idx])) {
                $make = cx_seo_make_from_slug($parts[$idx], $route['veh']);
                if ($make === null) {
                    return null;
                }
                $route['make'] = $make;
                $idx++;
            }
        }
        if ($idx < count($parts)) {
            return null;
        }

        return $route;
    }

    if (count($parts) < 2 || !cx_vehicle_browse_active($parts[1])) {
        return null;
    }

    $route = [
        'type' => 'arac',
        'region' => '',
        'city' => '',
        'veh' => $parts[1],
        'make' => '',
    ];
    if (isset($parts[2])) {
        $make = cx_seo_make_from_slug($parts[2], $route['veh']);
        if ($make === null) {
            return null;
        }
        $route['make'] = $make;
        if (isset($parts[3])) {
            return null;
        }
    }

    return $route;
}

/** @param array{type:string,region:string,city:string,veh:string,make:string} $route */
function cx_seo_route_apply(array $route): void
{
    $GLOBALS['cx_seo_canonical_route'] = true;

    if ($route['region'] === 'kktc') {
        $_GET['region'] = 'kktc';
    }
    if ($route['city'] !== '') {
        $_GET['city'] = $route['city'];
    }
    if ($route['veh'] !== '') {
        $_GET['veh'] = $route['veh'];
        if ($route['make'] !== '') {
            $_GET['make'] = [$route['make']];
            // SEO landing: marka URL'si dogrudan ilan listesi (model sihirbazi degil).
            $_GET['all_models'] = '1';
        }
    }
}

/**
 * @param array{type:string,region:string,city:string,veh:string,make:string} $route
 */
function cx_seo_route_url(array $route): string
{
    $parts = [];
    if ($route['region'] === 'kktc') {
        $parts[] = 'kktc';
        if ($route['city'] !== '') {
            $parts[] = $route['city'];
        }
        if ($route['veh'] !== '') {
            $parts[] = $route['veh'];
            if ($route['make'] !== '') {
                $parts[] = cx_seo_make_slug($route['make']);
            }
        }

        return '/' . implode('/', $parts);
    }

    if ($route['veh'] !== '') {
        $parts[] = 'arac';
        $parts[] = $route['veh'];
        if ($route['make'] !== '') {
            $parts[] = cx_seo_make_slug($route['make']);
        }

        return '/' . implode('/', $parts);
    }

    return '/index.php';
}

/** @param array{type:string,region:string,city:string,veh:string,make:string} $route */
function cx_seo_route_absolute_url(array $route): string
{
    $path = cx_seo_route_url($route);

    return cx_site_base_url() . $path;
}

function cx_seo_kktc_city_href(string $cityCode, string $veh = '', string $make = ''): string
{
    if (!cx_seo_landing_enabled()) {
        $params = cx_region_query_params();
        if ($cityCode !== '') {
            $params['city'] = $cityCode;
        }
        if ($veh !== '') {
            $params['veh'] = $veh;
        }
        if ($make !== '') {
            $params['make'] = [$make];
        }

        return '/index.php?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
    }

    return cx_seo_route_url([
        'type' => 'kktc',
        'region' => 'kktc',
        'city' => $cityCode,
        'veh' => $veh,
        'make' => $make,
    ]);
}

/** @return list<array{label:string,href:string}> */
function cx_seo_route_breadcrumbs(array $route): array
{
    $crumbs = [
        ['label' => 'Ana sayfa', 'href' => '/index.php'],
    ];

    if ($route['region'] === 'kktc') {
        $crumbs[] = [
            'label' => 'KKTC',
            'href' => cx_seo_route_url([
                'type' => 'kktc',
                'region' => 'kktc',
                'city' => '',
                'veh' => '',
                'make' => '',
            ]),
        ];
        if ($route['city'] !== '') {
            $crumbs[] = [
                'label' => cx_kktc_city_label($route['city']),
                'href' => cx_seo_route_url([
                    'type' => 'kktc',
                    'region' => 'kktc',
                    'city' => $route['city'],
                    'veh' => '',
                    'make' => '',
                ]),
            ];
        }
    }

    if ($route['veh'] !== '') {
        $vehLabel = cx_vehicle_segment_label($route['veh']);
        $vehRoute = $route;
        $vehRoute['make'] = '';
        $crumbs[] = ['label' => $vehLabel, 'href' => cx_seo_route_url($vehRoute)];
    }

    if ($route['make'] !== '') {
        $crumbs[] = [
            'label' => $route['make'],
            'href' => cx_seo_route_url($route),
        ];
    }

    return $crumbs;
}

/** @return list<string> */
function cx_seo_sitemap_paths(): array
{
    if (!cx_seo_landing_enabled()) {
        return ['/index.php'];
    }

    $paths = ['/', '/galeriler', '/kktc'];
    foreach (array_keys(cx_kktc_cities()) as $city) {
        $paths[] = cx_seo_route_url([
            'type' => 'kktc',
            'region' => 'kktc',
            'city' => $city,
            'veh' => '',
            'make' => '',
        ]);
    }

    $popularLimit = cx_seo_landing_settings()['popular_brands_per_segment'];
    foreach (cx_vehicle_segments() as $veh => $_seg) {
        if ($veh === 'tum-araclar') {
            continue;
        }
        $paths[] = cx_seo_route_url([
            'type' => 'arac',
            'region' => '',
            'city' => '',
            'veh' => $veh,
            'make' => '',
        ]);
        $brandCount = 0;
        foreach (cx_vehicle_brand_catalog($veh) as $brand) {
            if (empty($brand['popular']) && $brandCount >= $popularLimit) {
                continue;
            }
            if (!empty($brand['popular'])) {
                $paths[] = cx_seo_route_url([
                    'type' => 'arac',
                    'region' => '',
                    'city' => '',
                    'veh' => $veh,
                    'make' => $brand['name'],
                ]);
                $brandCount++;
            }
        }
        foreach (array_keys(cx_kktc_cities()) as $city) {
            $paths[] = cx_seo_route_url([
                'type' => 'kktc',
                'region' => 'kktc',
                'city' => $city,
                'veh' => $veh,
                'make' => '',
            ]);
        }
    }

    return array_values(array_unique($paths));
}
