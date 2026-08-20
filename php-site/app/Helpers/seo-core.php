<?php

declare(strict_types=1);

/**
 * BenimBazar — merkezi SEO / Schema / canonical yardimcilari.
 * Sahte isletme bilgisi uretmez; admin ayarlarindan gelen gercek veriyi kullanir.
 */

/** @return array<string,mixed> */
function cx_seo_settings(): array
{
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }

    $app = cx_app_config();
    $defaults = is_array($app['seo'] ?? null) ? $app['seo'] : [];
    $file = BASE_PATH . '/storage/seo-settings.json';
    $stored = [];
    if (is_file($file)) {
        $raw = json_decode((string) file_get_contents($file), true);
        if (is_array($raw)) {
            $stored = $raw;
        }
    }

    $cache = array_replace_recursive([
        'site_name' => cx_site_name(),
        'tagline' => 'Türkiye ve KKTC\'nin Araç ve İlan Pazaryeri',
        'default_title' => 'BenimBazar | Türkiye ve KKTC Araç İlanları',
        'default_description' => 'BenimBazar ile Türkiye ve KKTC\'de otomobil, motosiklet, bisiklet ve ticari araç ilanlarını keşfedin. Araç ilanı verin, satın veya takas seçeneklerini değerlendirin.',
        'search_url_template' => '/index.php?q={search_term_string}',
        'google_site_verification' => '',
        'yandex_site_verification' => '',
        'bing_site_verification' => '',
        'google_business_profile_url' => '',
        'google_maps_url' => '',
        'google_place_id' => '',
        'organization' => [
            'legal_name' => 'BenimBazar',
            'short_name' => 'BenimBazar',
            'description' => 'Türkiye ve KKTC odaklı dijital araç ve ilan pazaryeri.',
            'email' => '',
            'telephone' => '',
            'address_street' => '',
            'address_city' => '',
            'address_region' => '',
            'address_postal' => '',
            'address_country' => '',
            'service_areas' => '',
            'opening_hours' => '',
        ],
        'social' => [
            'facebook' => '',
            'instagram' => '',
            'youtube' => '',
            'tiktok' => '',
            'linkedin' => '',
            'x' => '',
        ],
    ], $defaults, $stored);

    return $cache;
}

/** Site kok URL — config + istek uzerinden HTTPS tercih. */
function cx_site_base_url(): string
{
    $cfg = rtrim((string) (cx_app_config()['url'] ?? ''), '/');
    if ($cfg !== '') {
        if (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') {
            $cfg = preg_replace('#^http:#i', 'https:', $cfg) ?? $cfg;
        }
        return $cfg;
    }
    $host = trim((string) ($_SERVER['HTTP_HOST'] ?? 'localhost'));
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    return $scheme . '://' . $host;
}

function cx_canonical_url(string $path): string
{
    $path = '/' . ltrim($path, '/');
    if ($path === '/index.php') {
        $path = '/';
    }
    return cx_site_base_url() . $path;
}

function cx_seo_absolute_url(string $pathOrUrl): string
{
    if (preg_match('#^https?://#i', $pathOrUrl)) {
        return $pathOrUrl;
    }
    return cx_canonical_url($pathOrUrl);
}

function cx_seo_logo_url(): string
{
    $logo = cx_brand_asset_path('logo_horizontal');
    if ($logo === '') {
        $logo = cx_brand_asset_path('logo_icon');
    }
    if ($logo === '') {
        return '';
    }
    if (str_starts_with($logo, 'http')) {
        return cx_seo_absolute_url($logo);
    }
    return cx_canonical_url($logo);
}

/** @return list<string> */
function cx_seo_same_as_links(): array
{
    $social = cx_seo_settings()['social'] ?? [];
    if (!is_array($social)) {
        return [];
    }
    $out = [];
    foreach ($social as $url) {
        $url = trim((string) $url);
        if ($url !== '' && preg_match('#^https?://#i', $url)) {
            $out[] = $url;
        }
    }
    $gbp = trim((string) (cx_seo_settings()['google_business_profile_url'] ?? ''));
    if ($gbp !== '' && preg_match('#^https?://#i', $gbp)) {
        $out[] = $gbp;
    }
    return array_values(array_unique($out));
}

/** @return array<string,mixed> */
function cx_seo_organization_schema(): array
{
    $s = cx_seo_settings();
    $org = is_array($s['organization'] ?? null) ? $s['organization'] : [];
    $base = cx_site_base_url() . '/';

    $schema = [
        '@context' => 'https://schema.org',
        '@type' => 'Organization',
        'name' => trim((string) ($org['legal_name'] ?? 'BenimBazar')),
        'url' => $base,
        'description' => trim((string) ($org['description'] ?? $s['tagline'] ?? '')),
    ];

    $logo = cx_seo_logo_url();
    if ($logo !== '') {
        $schema['logo'] = $logo;
    }

    $email = trim((string) ($org['email'] ?? ''));
    if ($email !== '' && str_contains($email, '@')) {
        $schema['email'] = $email;
    }

    $phone = trim((string) ($org['telephone'] ?? ''));
    if ($phone !== '') {
        $schema['telephone'] = $phone;
    }

    $street = trim((string) ($org['address_street'] ?? ''));
    $city = trim((string) ($org['address_city'] ?? ''));
    if ($street !== '' || $city !== '') {
        $addr = ['@type' => 'PostalAddress'];
        if ($street !== '') {
            $addr['streetAddress'] = $street;
        }
        if ($city !== '') {
            $addr['addressLocality'] = $city;
        }
        $region = trim((string) ($org['address_region'] ?? ''));
        if ($region !== '') {
            $addr['addressRegion'] = $region;
        }
        $postal = trim((string) ($org['address_postal'] ?? ''));
        if ($postal !== '') {
            $addr['postalCode'] = $postal;
        }
        $country = trim((string) ($org['address_country'] ?? ''));
        if ($country !== '') {
            $addr['addressCountry'] = $country;
        }
        $schema['address'] = $addr;
    }

    $sameAs = cx_seo_same_as_links();
    if ($sameAs !== []) {
        $schema['sameAs'] = $sameAs;
    }

    return $schema;
}

/** @return array<string,mixed> */
function cx_seo_website_schema(): array
{
    $s = cx_seo_settings();
    $base = cx_site_base_url() . '/';
    $schema = [
        '@context' => 'https://schema.org',
        '@type' => 'WebSite',
        'name' => trim((string) ($s['site_name'] ?? cx_site_name())),
        'url' => $base,
        'description' => trim((string) ($s['default_description'] ?? '')),
        'publisher' => [
            '@type' => 'Organization',
            'name' => trim((string) (($s['organization']['legal_name'] ?? '') ?: 'BenimBazar')),
            'url' => $base,
        ],
    ];

    $searchTpl = trim((string) ($s['search_url_template'] ?? ''));
    if ($searchTpl !== '' && str_contains($searchTpl, '{search_term_string}')) {
        $target = cx_seo_absolute_url($searchTpl);
        $schema['potentialAction'] = [
            '@type' => 'SearchAction',
            'target' => [
                '@type' => 'EntryPoint',
                'urlTemplate' => $target,
            ],
            'query-input' => 'required name=search_term_string',
        ];
    }

    return $schema;
}

/** @return array{title:string,description:string,canonical:string,json_ld:string} */
function cx_seo_home_meta(): array
{
    $s = cx_seo_settings();
    $org = cx_seo_organization_schema();
    $web = cx_seo_website_schema();
    $jsonLd = json_encode([$org, $web], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '[]';

    return [
        'title' => trim((string) ($s['default_title'] ?? 'BenimBazar | Türkiye ve KKTC Araç İlanları')),
        'description' => trim((string) ($s['default_description'] ?? '')),
        'canonical' => cx_canonical_url('/'),
        'json_ld' => $jsonLd,
    ];
}

/**
 * @param list<array{label:string,href:string}> $breadcrumbs
 */
function cx_seo_breadcrumb_json_ld(array $breadcrumbs): string
{
    $items = [];
    $pos = 1;
    foreach ($breadcrumbs as $crumb) {
        $href = cx_seo_absolute_url((string) ($crumb['href'] ?? ''));
        $items[] = [
            '@type' => 'ListItem',
            'position' => $pos,
            'name' => (string) ($crumb['label'] ?? ''),
            'item' => $href,
        ];
        $pos++;
    }
    $block = [
        '@context' => 'https://schema.org',
        '@type' => 'BreadcrumbList',
        'itemListElement' => $items,
    ];

    return json_encode($block, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '{}';
}

/**
 * @param array<string,mixed> $item
 * @return array{title:string,description:string,canonical:string,breadcrumbs:list<array{label:string,href:string}>,json_ld:string}
 */
function cx_listing_seo_meta(array $item, int $id, int $no): array
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = cx_listing_vehicle_make($item);
    $model = cx_listing_vehicle_model($item);
    $year = (int) ($vehicle['year'] ?? 0);
    $fuel = trim((string) ($vehicle['fuel'] ?? ''));
    $trans = trim((string) ($vehicle['transmission'] ?? ''));
    $segment = trim((string) ($attrs['segment'] ?? ''));

    $parts = array_filter([
        $year >= 1900 ? (string) $year : '',
        $make,
        $model,
        $fuel !== '' ? $fuel : '',
        $trans !== '' ? $trans : '',
    ], static fn ($v) => trim((string) $v) !== '');

    $headline = $parts !== [] ? implode(' ', $parts) : trim((string) ($item['title'] ?? 'İlan'));
    $title = $headline . ' | BenimBazar';

    $priceLine = cx_listing_price_line($item);
    $location = cx_listing_location_line($item);
    $km = isset($vehicle['km']) ? (int) $vehicle['km'] : -1;
    $descBits = array_filter([
        $headline . ' araç ilanı.',
        $priceLine !== '' && $priceLine !== 'Takas' ? 'Fiyat: ' . $priceLine . '.' : '',
        $km >= 0 ? number_format($km, 0, ',', '.') . ' km.' : '',
        $location !== '' ? 'Konum: ' . $location . '.' : '',
        'Detayları BenimBazar\'da inceleyin.',
    ]);
    $description = mb_substr(implode(' ', $descBits), 0, 160);

    $canonical = cx_canonical_url('/listing.php?id=' . $id);
    $breadcrumbs = [
        ['label' => 'Ana Sayfa', 'href' => '/'],
    ];
    if ($segment !== '' && isset(cx_vehicle_segments()[$segment])) {
        $breadcrumbs[] = [
            'label' => cx_vehicle_segment_label($segment),
            'href' => '/index.php?veh=' . rawurlencode($segment),
        ];
    }
    if ($make !== '') {
        $breadcrumbs[] = [
            'label' => $make,
            'href' => '/index.php?veh=' . rawurlencode($segment !== '' ? $segment : 'otomobil') . '&make%5B0%5D=' . rawurlencode($make),
        ];
    }
    $breadcrumbs[] = ['label' => $headline, 'href' => '/listing.php?id=' . $id];

    $jsonBlocks = [
        json_decode(cx_seo_breadcrumb_json_ld($breadcrumbs), true),
        cx_listing_json_ld($item, $id, $canonical),
    ];
    $jsonLd = json_encode(array_values(array_filter($jsonBlocks)), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?: '[]';

    return [
        'title' => $title,
        'description' => $description,
        'canonical' => $canonical,
        'breadcrumbs' => $breadcrumbs,
        'json_ld' => $jsonLd,
    ];
}

/**
 * @param array<string,mixed> $item
 * @return array<string,mixed>
 */
function cx_listing_json_ld(array $item, int $id, string $canonical): array
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = cx_listing_vehicle_make($item);
    $model = cx_listing_vehicle_model($item);
    $year = (int) ($vehicle['year'] ?? 0);
    $name = trim((string) ($item['title'] ?? 'Araç ilanı'));
    $imageUrl = cx_listing_og_image_url($id, cx_site_base_url());

    $offer = null;
    $price = cx_listing_effective_price($item);
    if ($price !== null && strtoupper((string) ($item['listing_mode'] ?? '')) === 'SALE') {
        $offer = [
            '@type' => 'Offer',
            'url' => $canonical,
            'price' => round($price['amount'], 2),
            'priceCurrency' => $price['currency'],
            'availability' => cx_listing_is_sold((string) ($item['status'] ?? ''))
                ? 'https://schema.org/SoldOut'
                : 'https://schema.org/InStock',
        ];
    }

    $product = [
        '@context' => 'https://schema.org',
        '@type' => 'Product',
        'name' => $name,
        'url' => $canonical,
        'description' => mb_substr(trim((string) ($item['description'] ?? '')), 0, 500),
        'category' => trim((string) ($item['category'] ?? 'Araç')),
    ];
    if ($make !== '') {
        $product['brand'] = ['@type' => 'Brand', 'name' => $make];
    }
    if ($model !== '') {
        $product['model'] = $model;
    }
    if ($year >= 1900) {
        $product['releaseDate'] = (string) $year;
    }
    if ($imageUrl !== '') {
        $product['image'] = cx_listing_og_image_public_url($imageUrl, cx_app_config());
    }
    if ($offer !== null) {
        $product['offers'] = $offer;
    }

    return $product;
}

/** @param array<string,mixed> $item */
function cx_listing_photo_alt(array $item, int $index = 0): string
{
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $parts = array_filter([
        isset($vehicle['year']) ? (string) (int) $vehicle['year'] : '',
        cx_listing_vehicle_make($item),
        cx_listing_vehicle_model($item),
        trim((string) ($vehicle['fuel'] ?? '')),
    ], static fn ($v) => trim((string) $v) !== '');
    $base = $parts !== [] ? implode(' ', $parts) . ' araç' : trim((string) ($item['title'] ?? 'Araç ilanı'));
    if ($index > 0) {
        return $base . ' — fotoğraf ' . ($index + 1);
    }
    return $base;
}

function cx_seo_robots_noindex(): string
{
    return 'noindex, nofollow';
}

function cx_seo_robots_index(): string
{
    return 'index, follow';
}

/** Filtre / oturum URL'leri icin noindex oner. */
function cx_seo_should_noindex_query_page(): bool
{
    if (!empty($GLOBALS['cx_seo_canonical_route'])) {
        return false;
    }

    $privateKeys = ['q', 'sort', 'page', 'show_sold', 'region', 'city', 'make', 'model', 'year_min', 'year_max', 'price_min', 'price_max'];
    foreach ($privateKeys as $key) {
        if (isset($_GET[$key]) && (string) $_GET[$key] !== '') {
            if ($key === 'veh' || $key === '__seo_path') {
                continue;
            }
            if ($key === 'region' && in_array((string) $_GET[$key], ['kktc', 'all', ''], true)) {
                continue;
            }
            return true;
        }
    }
    return false;
}

function cx_seo_google_profile_link(): string
{
    $url = trim((string) (cx_seo_settings()['google_business_profile_url'] ?? ''));
    return ($url !== '' && preg_match('#^https?://#i', $url)) ? $url : '';
}

function cx_seo_google_maps_link(): string
{
    $url = trim((string) (cx_seo_settings()['google_maps_url'] ?? ''));
    return ($url !== '' && preg_match('#^https?://#i', $url)) ? $url : '';
}

function cx_seo_auto_noindex(): ?string
{
    $script = basename((string) ($_SERVER['SCRIPT_NAME'] ?? ''));
    $private = [
        'login.php', 'register.php', 'forgot-password.php', 'logout.php',
        'messages.php', 'conversation.php', 'message-send.php', 'notifications.php',
        'favorites.php', 'my-listings.php', 'create-listing.php', 'edit-listing.php',
        'gallery-panel.php', 'verify-phone.php', 'share.php', 'share-card.php',
        'share-og.php', 'kurulum.php', 'test.php', 'info.php', 'install.php',
        'migrate-user-columns.php', 'listing-action.php', 'favorite-toggle.php',
        'follow-toggle.php', 'alert-toggle.php',
    ];
    if (str_starts_with((string) ($_SERVER['SCRIPT_NAME'] ?? ''), '/admin/') || str_starts_with($script, 'admin')) {
        return cx_seo_robots_noindex();
    }
    if (in_array($script, $private, true)) {
        return cx_seo_robots_noindex();
    }
    if ($script === 'index.php' && cx_seo_should_noindex_query_page()) {
        return cx_seo_robots_noindex();
    }
    return null;
}

/** Webmaster dogrulama meta etiketleri (Google, Yandex, Bing/Yahoo). */
function cx_seo_verification_metas(): array
{
    $s = cx_seo_settings();
    $map = [
        'google_site_verification' => 'google-site-verification',
        'yandex_site_verification' => 'yandex-verification',
        'bing_site_verification' => 'msvalidate.01',
    ];
    $out = [];
    foreach ($map as $key => $name) {
        $content = trim((string) ($s[$key] ?? ''));
        if ($content !== '') {
            $out[] = ['name' => $name, 'content' => $content];
        }
    }

    return $out;
}

/** Yandex Host robots satiri icin ana domain. */
function cx_seo_yandex_host(): string
{
    $base = cx_site_base_url();
    $host = (string) (parse_url($base, PHP_URL_HOST) ?? '');
    return strtolower(trim($host));
}

/** robots.txt govdesi — tum arama motorlari + Yandex Host/Clean-param. */
function cx_seo_robots_txt_body(): string
{
    $base = cx_site_base_url();
    $host = cx_seo_yandex_host();
    $disallow = [
        '/admin/',
        '/login.php',
        '/register.php',
        '/forgot-password.php',
        '/messages.php',
        '/conversation.php',
        '/notifications.php',
        '/favorites.php',
        '/my-listings.php',
        '/create-listing.php',
        '/edit-listing.php',
        '/gallery-panel.php',
        '/kurulum.php',
        '/test.php',
        '/share.php',
        '/share-card.php',
        '/share-og.php',
    ];

    $lines = [];
    if ($host !== '') {
        $lines[] = '# Yandex — tercih edilen ana domain';
        $lines[] = 'Host: ' . $host;
        $lines[] = '';
        $lines[] = '# Yandex — filtre/oturum parametrelerini tek URL altinda birlestir';
        $lines[] = 'Clean-param: q&sort&page&region&city&show_sold&make&model&year_min&year_max&price_min&price_max /index.php';
        $lines[] = '';
    }

    foreach (['Yandex', 'Googlebot', 'bingbot', 'Slurp', '*'] as $ua) {
        $lines[] = 'User-agent: ' . $ua;
        $lines[] = 'Allow: /';
        foreach ($disallow as $path) {
            $lines[] = 'Disallow: ' . $path;
        }
        $lines[] = '';
    }

    $lines[] = 'Sitemap: ' . $base . '/sitemap.php';
    $lines[] = 'Sitemap: ' . $base . '/sitemap-listings.php';

    return implode("\n", $lines) . "\n";
}
