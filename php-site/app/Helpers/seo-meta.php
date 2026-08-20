<?php

declare(strict_types=1);

require_once __DIR__ . '/seo-routes.php';

/**
 * @param array{type:string,region:string,city:string,veh:string,make:string} $route
 * @return array{title:string,description:string,canonical:string,h1:string,breadcrumbs:list<array{label:string,href:string}>,json_ld:string}
 */
function cx_seo_meta_for_route(array $route, int $listingCount = 0): array
{
    $site = cx_site_name();
    $cityLabel = $route['city'] !== '' ? cx_kktc_city_label($route['city']) : '';
    $vehLabel = $route['veh'] !== '' ? cx_vehicle_segment_label($route['veh']) : '';
    $make = $route['make'];

    $titleParts = [];
    $descParts = [];

    if ($make !== '') {
        $titleParts[] = $make;
    }
    if ($vehLabel !== '') {
        $titleParts[] = $vehLabel;
    }
    if ($cityLabel !== '') {
        $titleParts[] = $cityLabel;
    } elseif ($route['region'] === 'kktc') {
        $titleParts[] = 'KKTC';
    }

    if ($titleParts === []) {
        $h1 = 'İlanlar';
        $title = 'İlanlar';
        $description = 'Al, sat, kazançlı çık! BenimBazar\'da araç, motosiklet ve takas ilanları.';
    } else {
        $h1 = implode(' ', $titleParts) . ' ilanları';
        $title = implode(' ', $titleParts) . ' İlanları';
        $description = implode(' ', $titleParts)
            . ' bölgesinde satılık ve takas ilanları. '
            . ($route['region'] === 'kktc' ? 'Sterlin (£) ve TL fiyatlı KKTC araç ilanları. ' : '')
            . 'BenimBazar\'da güncel ilanları inceleyin.';
    }

    if ($listingCount > 0) {
        $description .= ' Şu an ' . number_format($listingCount, 0, ',', '.') . ' ilan listeleniyor.';
    }

    $canonical = cx_seo_route_absolute_url($route);
    $breadcrumbs = cx_seo_route_breadcrumbs($route);

    $jsonLd = [
        '@context' => 'https://schema.org',
        '@type' => 'CollectionPage',
        'name' => $h1,
        'description' => $description,
        'url' => $canonical,
        'isPartOf' => [
            '@type' => 'WebSite',
            'name' => $site,
            'url' => cx_site_base_url() . '/',
        ],
        'breadcrumb' => [
            '@type' => 'BreadcrumbList',
            'itemListElement' => [],
        ],
    ];

    $pos = 1;
    foreach ($breadcrumbs as $crumb) {
        $href = (string) $crumb['href'];
        if (!str_starts_with($href, 'http')) {
            $href = cx_site_base_url() . $href;
        }
        $jsonLd['breadcrumb']['itemListElement'][] = [
            '@type' => 'ListItem',
            'position' => $pos,
            'name' => $crumb['label'],
            'item' => $href,
        ];
        $pos++;
    }

    return [
        'title' => $title,
        'description' => $description,
        'canonical' => $canonical,
        'h1' => $h1,
        'breadcrumbs' => $breadcrumbs,
        'json_ld' => json_encode($jsonLd, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '{}',
    ];
}

/** @return array{title:string,description:string,canonical:string} */
function cx_gallery_directory_seo_meta(int $total = 0, string $cityFilter = ''): array
{
    $title = $cityFilter !== ''
        ? $cityFilter . ' Galerileri'
        : 'Galeriler ve Mağazalar';
    $description = 'KKTC ve Türkiye\'deki kurumsal araç galerileri ve VIP mağazalar. ';
    if ($cityFilter !== '') {
        $description = $cityFilter . ' bölgesindeki güvenilir araç galerileri. ';
    }
    $description .= 'BenimBazar mağaza vitrinlerini keşfedin.';
    if ($total > 0) {
        $description .= ' ' . number_format($total, 0, ',', '.') . ' mağaza.';
    }

    $base = cx_site_base_url();
    $canonical = $base . '/galeriler';
    if ($cityFilter !== '') {
        $canonical .= '?city=' . rawurlencode($cityFilter);
    }

    return [
        'title' => $title,
        'description' => $description,
        'canonical' => $canonical,
    ];
}

/**
 * @param array<string,mixed> $owner
 * @param array<string,mixed> $stats
 * @return array<string,string>
 */
function cx_gallery_open_graph(array $owner, array $stats): array
{
    $displayName = (string) ($owner['display_name'] ?? $owner['username'] ?? 'Galeri');
    $city = trim((string) ($owner['city'] ?? ''));
    $about = trim((string) ($owner['about'] ?? ''));
    $listingN = (int) ($stats['listings'] ?? 0);
    $siteUrl = rtrim((string) (cx_app_config()['url'] ?? ''), '/');
    $pageUrl = $siteUrl . '/galeri.php?id=' . (int) ($owner['id'] ?? 0);

    $headline = $displayName . ($city !== '' ? ' — ' . $city : '') . ' Mağazası';
    $description = $about !== ''
        ? mb_substr($about, 0, 180)
        : ($listingN . ' yayındaki ilan · BenimBazar kurumsal mağaza');

    $uploadsUrl = (string) (cx_app_config()['uploads_url'] ?? '/uploads');
    $bannerRaw = (string) ($stats['banner'] ?? '');
    $imageUrl = '';
    if ($bannerRaw !== '') {
        if (preg_match('#^https?://#i', $bannerRaw)) {
            $imageUrl = $bannerRaw;
        } elseif (str_starts_with($bannerRaw, '/')) {
            $imageUrl = $siteUrl . $bannerRaw;
        } else {
            $imageUrl = cx_user_avatar_src($bannerRaw, $uploadsUrl);
            if ($imageUrl !== '' && !str_starts_with($imageUrl, 'http')) {
                $imageUrl = $siteUrl . $imageUrl;
            }
        }
    }
    if ($imageUrl === '') {
        $logo = cx_user_avatar_src((string) ($owner['avatar_url'] ?? ''), $uploadsUrl);
        if ($logo !== '' && !str_starts_with($logo, 'http')) {
            $imageUrl = $siteUrl . $logo;
        } else {
            $imageUrl = $logo;
        }
    }
    if ($imageUrl === '') {
        $imageUrl = cx_listing_og_image_url(0, $siteUrl);
    } else {
        $imageUrl = cx_listing_og_image_public_url($imageUrl, cx_app_config());
    }

    return [
        'og:type' => 'website',
        'og:site_name' => cx_site_name(),
        'og:title' => $headline,
        'og:description' => $description,
        'og:url' => $pageUrl,
        'og:image' => $imageUrl,
        'twitter:card' => 'summary_large_image',
        'twitter:title' => $headline,
        'twitter:description' => $description,
        'twitter:image' => $imageUrl,
    ];
}

/** @return array{enabled:bool,featured_vip:int,featured_dealer:int,per_page:int} */
function cx_gallery_discovery_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['gallery_discovery'] ?? null) ? $app['gallery_discovery'] : [];

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'featured_vip' => max(0, min(12, (int) ($cfg['featured_vip'] ?? 6))),
        'featured_dealer' => max(0, min(12, (int) ($cfg['featured_dealer'] ?? 6))),
        'per_page' => max(12, min(48, (int) ($cfg['per_page'] ?? 24))),
    ];
}

function cx_gallery_discovery_enabled(): bool
{
    return cx_gallery_discovery_settings()['enabled'];
}
