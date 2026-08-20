<?php

declare(strict_types=1);

/** @return array<string,mixed> */
function cx_feed_ads_settings(): array
{
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }

    $app = cx_app_config();
    $cfg = is_array($app['feed_ads'] ?? null) ? $app['feed_ads'] : [];
    $defaults = [
        'enabled' => true,
        'insert_after' => 4,
        'rotate_interval_ms' => 7000,
        'house_ads' => [
            [
                'id' => 'house-ilan-ver',
                'kind' => 'house',
                'theme' => 'blue',
                'text' => 'Ürünlerini burada görmek ister misin? BenimBazar\'da yerini al — al, sat, kazançlı çık!',
                'button' => 'ilan ver',
                'href' => '{create_listing}',
                'label' => 'BenimBazar ilan ver',
            ],
            [
                'id' => 'house-galeri',
                'kind' => 'house',
                'theme' => 'blue',
                'text' => 'Galerin mi var? BenimBazar\'da kurumsal vitrin aç — binlerce alıcıya ulaş.',
                'button' => 'Galeriler',
                'href' => '/galeriler.php',
                'label' => 'BenimBazar galeriler',
            ],
            [
                'id' => 'house-takas',
                'kind' => 'house',
                'theme' => 'blue',
                'text' => 'Takas mı satış mı? İlanını ücretsiz yayınla, teklifleri BenimBazar\'da topla.',
                'button' => 'Keşfet',
                'href' => '/index.php?veh=tum-araclar',
                'label' => 'BenimBazar araç ilanları',
            ],
        ],
        'sponsored' => [],
    ];

    $stored = [];
    $file = BASE_PATH . '/storage/feed-ads.json';
    if (is_file($file)) {
        $raw = json_decode((string) file_get_contents($file), true);
        if (is_array($raw)) {
            $stored = $raw;
        }
    }

    $cache = array_replace_recursive($defaults, $cfg, $stored);

    return $cache;
}

function cx_feed_ad_insert_after(): int
{
    $cfg = cx_feed_ads_settings();

    return max(0, (int) ($cfg['insert_after'] ?? 4));
}

/** @param array<string,mixed> $ad */
function cx_feed_ad_is_active(array $ad): bool
{
    if (array_key_exists('enabled', $ad) && empty($ad['enabled'])) {
        return false;
    }

    $now = time();
    $start = trim((string) ($ad['starts_at'] ?? ''));
    $end = trim((string) ($ad['ends_at'] ?? ''));

    if ($start !== '') {
        $ts = strtotime($start);
        if ($ts !== false && $now < $ts) {
            return false;
        }
    }
    if ($end !== '') {
        $ts = strtotime($end);
        if ($ts !== false && $now > $ts) {
            return false;
        }
    }

    return trim((string) ($ad['text'] ?? '')) !== '' || trim((string) ($ad['image_url'] ?? '')) !== '';
}

/**
 * @param array<string,mixed> $ad
 * @return array{id:string,kind:string,theme:string,text:string,button:string,href:string,label:string,image_url:string,external:bool}
 */
function cx_feed_ad_normalize(array $ad, ?array $user, string $createHref): array
{
    $href = trim((string) ($ad['href'] ?? ''));
    if ($href === '{create_listing}' || $href === '') {
        $href = $createHref;
    }
    if (!$user && (str_starts_with($href, '/create-listing') || str_contains($href, 'create-listing'))) {
        $href = cx_login_url($createHref, 'İlan vermek için giriş yapın');
    }

    $external = preg_match('#^https?://#i', $href) === 1;

    return [
        'id' => trim((string) ($ad['id'] ?? 'ad-' . substr(md5(json_encode($ad)), 0, 8))),
        'kind' => trim((string) ($ad['kind'] ?? 'house')),
        'theme' => trim((string) ($ad['theme'] ?? 'blue')),
        'text' => trim((string) ($ad['text'] ?? '')),
        'button' => trim((string) ($ad['button'] ?? 'Detay')),
        'href' => $href,
        'label' => trim((string) ($ad['label'] ?? 'Reklam')),
        'image_url' => trim((string) ($ad['image_url'] ?? '')),
        'image_focus' => trim((string) ($ad['image_focus'] ?? '68% 42%')),
        'external' => $external,
    ];
}

/** @return list<array<string,mixed>> */
function cx_feed_ads_for_grid(?array $user, string $createHref = '/create-listing.php'): array
{
    $cfg = cx_feed_ads_settings();
    if (empty($cfg['enabled'])) {
        return [];
    }

    $ads = [];
    foreach (is_array($cfg['sponsored'] ?? null) ? $cfg['sponsored'] : [] as $sp) {
        if (!is_array($sp) || !cx_feed_ad_is_active($sp)) {
            continue;
        }
        $ads[] = cx_feed_ad_normalize($sp, $user, $createHref);
    }

    foreach (is_array($cfg['house_ads'] ?? null) ? $cfg['house_ads'] : [] as $house) {
        if (!is_array($house)) {
            continue;
        }
        $ads[] = cx_feed_ad_normalize($house, $user, $createHref);
    }

    return $ads;
}

function cx_feed_ad_rotate_interval_ms(): int
{
    $cfg = cx_feed_ads_settings();

    return max(3000, min(60000, (int) ($cfg['rotate_interval_ms'] ?? 7000)));
}
