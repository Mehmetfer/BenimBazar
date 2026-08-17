<?php

declare(strict_types=1);

function cx_e(?string $s): string
{
    return htmlspecialchars((string) $s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function cx_site_name(): string
{
    return (string) (cx_app_config()['name'] ?? 'BenimBazar');
}

function cx_site_tagline(): string
{
    return (string) (cx_app_config()['tagline'] ?? 'Al, sat, kazançlı çık!');
}

function cx_brand_asset_path(string $key): string
{
    $assets = cx_app_config()['brand_assets'] ?? [];

    return (string) ($assets[$key] ?? '');
}

function cx_brand_asset_url(string $key): string
{
    $path = cx_brand_asset_path($key);
    if ($path === '') {
        return '';
    }
    if (str_starts_with($path, 'http://') || str_starts_with($path, 'https://')) {
        return $path;
    }

    return rtrim((string) (cx_app_config()['url'] ?? ''), '/') . $path;
}

function cx_listing_no(int $id, int $base = 1000000000): int
{
    return $base + $id;
}

function cx_parse_listing_no(string $raw, int $base = 1000000000): ?int
{
    $q = preg_replace('/[\s.]/', '', trim($raw)) ?? '';
    if ($q === '' || !ctype_digit($q)) {
        return null;
    }
    $n = (int) $q;
    if ($n > $base) {
        return $n - $base;
    }
    return $n > 0 ? $n : null;
}

/** @param mixed $raw */
function cx_photo_urls($raw, string $uploadsUrl = '/uploads'): array
{
    if (is_array($raw)) {
        $list = $raw;
    } else {
        $list = json_decode((string) $raw, true);
        if (!is_array($list)) {
            $list = [];
        }
    }
    $out = [];
    foreach ($list as $u) {
        $u = (string) $u;
        if ($u === '') {
            continue;
        }
        if (str_starts_with($u, 'http://') || str_starts_with($u, 'https://')) {
            $out[] = cx_photo_original($u);
        } elseif (str_starts_with($u, '/')) {
            $out[] = cx_photo_original($u);
        } else {
            $out[] = cx_photo_original(rtrim($uploadsUrl, '/') . '/' . ltrim($u, '/'));
        }
    }
    return $out;
}

/** @param mixed $raw @return list<string> */
function cx_listing_photo_stubs($raw): array
{
    if (is_array($raw)) {
        $list = $raw;
    } else {
        $list = json_decode((string) $raw, true);
        if (!is_array($list)) {
            $list = [];
        }
    }
    $out = [];
    foreach ($list as $u) {
        $u = trim((string) $u);
        if ($u !== '') {
            $out[] = $u;
        }
    }

    return $out;
}

/** @param array<string,mixed> $post @param list<string> $existingRaw @return list<string> */
function cx_listing_photos_from_keep(array $post, array $existingRaw): array
{
    $existingRaw = cx_listing_photo_stubs($existingRaw);
    if (!isset($post['keep_photos']) || !is_array($post['keep_photos'])) {
        if (isset($post['photo_editor'])) {
            return [];
        }

        return $existingRaw;
    }
    $allowed = array_flip($existingRaw);
    $photos = [];
    foreach ($post['keep_photos'] as $stub) {
        $stub = (string) $stub;
        if ($stub !== '' && isset($allowed[$stub])) {
            $photos[] = $stub;
        }
    }

    return $photos;
}

/** @return list<string> */
function cx_listing_save_uploaded_photos(array $files, int $userId): array
{
    $app = cx_app_config();
    $uploadDir = (string) ($app['uploads_path'] ?? (BASE_PATH . '/uploads'));
    if (!is_dir($uploadDir)) {
        @mkdir($uploadDir, 0755, true);
    }
    $maxBytes = (int) ($app['max_upload_bytes'] ?? 5242880);
    $allowed = $app['allowed_upload_types'] ?? ['image/jpeg', 'image/png', 'image/webp'];
    $saved = [];
    if (empty($files['name'][0])) {
        return $saved;
    }
    foreach ($files['name'] as $i => $name) {
        if ((int) ($files['error'][$i] ?? 1) !== UPLOAD_ERR_OK) {
            continue;
        }
        if ((int) ($files['size'][$i] ?? 0) > $maxBytes) {
            continue;
        }
        $tmp = (string) ($files['tmp_name'][$i] ?? '');
        $mime = (string) (@mime_content_type($tmp) ?: '');
        if (!in_array($mime, $allowed, true)) {
            continue;
        }
        $ext = $mime === 'image/png' ? 'png' : ($mime === 'image/webp' ? 'webp' : 'jpg');
        $fname = 'listing_' . $userId . '_' . bin2hex(random_bytes(8)) . '.' . $ext;
        if (@move_uploaded_file($tmp, $uploadDir . '/' . $fname)) {
            require_once dirname(__DIR__) . '/Services/PhotoWatermarkService.php';
            \App\Services\PhotoWatermarkService::applyToFile($uploadDir . '/' . $fname);
            $saved[] = $fname;
        }
    }

    return $saved;
}

/**
 * Ekspertiz raporu sayfa fotograflari (filigransiz).
 *
 * @return list<string>
 */
function cx_listing_save_uploaded_expertise(array $files, int $userId): array
{
    $app = cx_app_config();
    $uploadDir = (string) ($app['uploads_path'] ?? (BASE_PATH . '/uploads'));
    if (!is_dir($uploadDir)) {
        @mkdir($uploadDir, 0755, true);
    }
    $maxBytes = (int) ($app['max_upload_bytes'] ?? 5242880);
    $allowed = $app['allowed_upload_types'] ?? ['image/jpeg', 'image/png', 'image/webp'];
    $saved = [];
    if (empty($files['name'][0])) {
        return $saved;
    }
    $count = 0;
    foreach ($files['name'] as $i => $name) {
        if ($count >= 12) {
            break;
        }
        if ((int) ($files['error'][$i] ?? 1) !== UPLOAD_ERR_OK) {
            continue;
        }
        if ((int) ($files['size'][$i] ?? 0) > $maxBytes) {
            continue;
        }
        $tmp = (string) ($files['tmp_name'][$i] ?? '');
        $mime = (string) (@mime_content_type($tmp) ?: '');
        if (!in_array($mime, $allowed, true)) {
            continue;
        }
        $ext = $mime === 'image/png' ? 'png' : ($mime === 'image/webp' ? 'webp' : 'jpg');
        $fname = 'expertise_' . $userId . '_' . bin2hex(random_bytes(8)) . '.' . $ext;
        if (@move_uploaded_file($tmp, $uploadDir . '/' . $fname)) {
            $saved[] = $fname;
            $count++;
        }
    }

    return $saved;
}

/**
 * @return array<string,string> part_id => label
 */
function cx_expertise_body_parts(): array
{
    return [
        'front_bumper' => 'Ön tampon',
        'hood' => 'Kaput',
        'roof' => 'Tavan',
        'trunk' => 'Bagaj kapağı',
        'rear_bumper' => 'Arka tampon',
        'fl_fender' => 'Sol ön çamurluk',
        'fr_fender' => 'Sağ ön çamurluk',
        'fl_door' => 'Sol ön kapı',
        'fr_door' => 'Sağ ön kapı',
        'rl_door' => 'Sol arka kapı',
        'rr_door' => 'Sağ arka kapı',
        'rl_quarter' => 'Sol arka çamurluk',
        'rr_quarter' => 'Sağ arka çamurluk',
    ];
}

/** @return list<string> */
function cx_expertise_part_statuses(): array
{
    return [
        'Orijinal',
        'Boyalı',
        'Lokal boyalı',
        'Plastik',
        'Değişmiş',
        'Sökme/takma',
        'Vernik',
        'Ezik',
    ];
}

/** @return array<string,string> status => kısaltma (ekspertiz raporu tarzı) */
function cx_expertise_status_abbrevs(): array
{
    return [
        'Orijinal' => 'O',
        'Boyalı' => 'B',
        'Lokal boyalı' => 'LB',
        'Plastik' => 'P',
        'Değişmiş' => 'D',
        'Sökme/takma' => 'ST',
        'Vernik' => 'V',
        'Ezik' => 'E',
        // Eski kayıtlar
        'Değişen' => 'D',
        'Plastik boyalı' => 'P',
    ];
}

/** @return array<string,string> eski durum → güncel durum */
function cx_expertise_status_normalize(string $status): string
{
    $map = [
        'Değişen' => 'Değişmiş',
        'Plastik boyalı' => 'Plastik',
    ];

    return $map[$status] ?? $status;
}

/**
 * @param array<string,mixed> $post
 * @return array<string,string>
 */
function cx_expertise_parts_from_post(array $post): array
{
    $allowedParts = cx_expertise_body_parts();
    $allowedStatus = array_flip(cx_expertise_part_statuses());
    $raw = $post['expertise_parts'] ?? null;
    if (!is_array($raw)) {
        return [];
    }
    $out = [];
    foreach ($raw as $partId => $status) {
        $partId = trim((string) $partId);
        $status = cx_expertise_status_normalize(trim((string) $status));
        if ($partId === '' || $status === '' || !isset($allowedParts[$partId])) {
            continue;
        }
        if (!isset($allowedStatus[$status])) {
            continue;
        }
        $out[$partId] = $status;
    }

    return $out;
}

/**
 * @param list<string> $kept
 * @param list<string> $newSaved
 * @return array{has_report:bool,photos:list<string>,parts:array<string,string>}|null
 */
function cx_listing_expertise_from_post(array $post, array $kept = [], array $newSaved = []): ?array
{
    $photos = array_values(array_unique(array_merge(
        cx_listing_photo_stubs($kept),
        cx_listing_photo_stubs($newSaved)
    )));
    $parts = cx_expertise_parts_from_post($post);
    $has = !empty($post['expertise_has']) || $photos !== [] || $parts !== [];
    if (!$has) {
        return null;
    }

    $pack = [
        'has_report' => true,
        'photos' => $photos,
    ];
    if ($parts !== []) {
        $pack['parts'] = $parts;
    }

    return $pack;
}

/**
 * @param list<string> $existingRaw
 * @return list<string>
 */
function cx_listing_expertise_kept_from_post(array $post, array $existingRaw): array
{
    $existingRaw = cx_listing_photo_stubs($existingRaw);
    if ($existingRaw === []) {
        return [];
    }
    if (!isset($post['keep_expertise']) || !is_array($post['keep_expertise'])) {
        return [];
    }
    $allowed = array_flip($existingRaw);
    $photos = [];
    foreach ($post['keep_expertise'] as $stub) {
        $stub = (string) $stub;
        if ($stub !== '' && isset($allowed[$stub])) {
            $photos[] = $stub;
        }
    }

    return $photos;
}

/** @return array{has_report:bool,photos:list<string>,parts:array<string,string>} */
function cx_listing_expertise(array $item): array
{
    $attrs = cx_listing_attrs($item);
    $ex = is_array($attrs['expertise'] ?? null) ? $attrs['expertise'] : [];
    $photos = [];
    if (!empty($ex['photos']) && is_array($ex['photos'])) {
        $photos = cx_listing_photo_stubs($ex['photos']);
    }
    $parts = [];
    if (!empty($ex['parts']) && is_array($ex['parts'])) {
        $allowed = cx_expertise_body_parts();
        $allowedStatus = array_flip(cx_expertise_part_statuses());
        foreach ($ex['parts'] as $partId => $status) {
            $partId = trim((string) $partId);
            $status = cx_expertise_status_normalize(trim((string) $status));
            if (isset($allowed[$partId]) && isset($allowedStatus[$status])) {
                $parts[$partId] = $status;
            }
        }
    }

    return [
        'has_report' => !empty($ex['has_report']) || $photos !== [] || $parts !== [],
        'photos' => $photos,
        'parts' => $parts,
    ];
}

/** @param list<string> $photos */
function cx_listing_photos_apply_cover(array $photos, ?string $coverStub): array
{
    if ($photos === []) {
        return [];
    }
    $coverStub = trim((string) ($coverStub ?? ''));
    if ($coverStub === '') {
        return array_values($photos);
    }
    $idx = array_search($coverStub, $photos, true);
    if ($idx === false || $idx === 0) {
        return array_values($photos);
    }
    $picked = $photos[$idx];
    unset($photos[$idx]);

    return array_values(array_merge([$picked], $photos));
}

/**
 * @param list<string> $kept
 * @param list<string> $newSaved
 * @param array<string,mixed> $post
 * @return list<string>
 */
function cx_listing_photos_finalize(array $kept, array $newSaved, array $post): array
{
    $photos = array_merge($kept, $newSaved);
    if ($photos === []) {
        return [];
    }

    $coverStub = null;
    $coverNew = trim((string) ($post['cover_photo_new'] ?? ''));
    if ($coverNew !== '' && preg_match('/^__new_(\d+)__$/', $coverNew, $m)) {
        $i = (int) $m[1];
        if (isset($newSaved[$i])) {
            $coverStub = $newSaved[$i];
        }
    }
    if ($coverStub === null) {
        $cover = trim((string) ($post['cover_photo'] ?? ''));
        if ($cover !== '' && in_array($cover, $photos, true)) {
            $coverStub = $cover;
        }
    }

    return cx_listing_photos_apply_cover($photos, $coverStub);
}

/** Orijinal URL (Unsplash ?w= vb. parametreler temizlenir). */
function cx_photo_original(string $url): string
{
    $url = trim($url);
    if ($url === '') {
        return '';
    }
    if (preg_match('#^https?://images\.unsplash\.com/#i', $url)) {
        $parts = parse_url($url);
        if (!is_array($parts)) {
            return $url;
        }
        $scheme = (string) ($parts['scheme'] ?? 'https');
        $host = (string) ($parts['host'] ?? 'images.unsplash.com');
        $path = (string) ($parts['path'] ?? '');

        return $scheme . '://' . $host . $path;
    }

    return $url;
}

/** @return array{thumb:int,card:int,detail:int} */
function cx_photo_widths(): array
{
    return ['thumb' => 400, 'card' => 800, 'detail' => 1600];
}

function cx_photo_sized(string $url, int $width, string $siteUrl = '', string $uploadsUrl = '/uploads'): string
{
    $original = cx_photo_original($url);
    if ($original === '') {
        return '';
    }
    if ($siteUrl === '') {
        $cfg = cx_app_config();
        $siteUrl = (string) ($cfg['url'] ?? '');
        $uploadsUrl = (string) ($cfg['uploads_url'] ?? '/uploads');
    }
    $width = max(1, $width);

    if (preg_match('#^https?://images\.unsplash\.com/#i', $original)) {
        return $original . '?w=' . $width . '&q=82&auto=format&fit=crop';
    }

    $abs = $original;
    if (!preg_match('#^https?://#i', $original)) {
        if (str_starts_with($original, '/')) {
            $abs = rtrim($siteUrl, '/') . $original;
        } else {
            $abs = rtrim($siteUrl, '/') . rtrim($uploadsUrl, '/') . '/' . ltrim($original, '/');
        }
    }

    if ($siteUrl !== '' && preg_match('#^https?://#i', $abs)) {
        return 'https://images.weserv.nl/?url=' . rawurlencode($abs)
            . '&w=' . $width . '&fit=cover&output=jpg&q=82';
    }

    return $original;
}

/** @param list<int>|null $widths */
function cx_photo_srcset(string $url, ?array $widths = null, string $siteUrl = '', string $uploadsUrl = '/uploads'): string
{
    $widths = $widths ?? array_values(cx_photo_widths());
    $parts = [];
    foreach ($widths as $w) {
        $parts[] = cx_photo_sized($url, (int) $w, $siteUrl, $uploadsUrl) . ' ' . (int) $w . 'w';
    }

    return implode(', ', $parts);
}

function cx_photo_sizes_for(string $context): string
{
    return match ($context) {
        'thumb' => '80px',
        'card' => '(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 320px',
        'detail' => '(max-width: 768px) 100vw, (max-width: 1200px) 66vw, 800px',
        'hero' => '100vw',
        default => '100vw',
    };
}

/** @return array{enabled:bool,logo:string,opacity_detail:float,opacity_card:float,opacity_thumb:float,blur_px:float,rotate_deg:float} */
function cx_photo_watermark_config(): array
{
    $cfg = cx_app_config();
    $wm = is_array($cfg['photo_watermark'] ?? null) ? $cfg['photo_watermark'] : [];
    $logo = trim((string) ($wm['logo'] ?? ''));
    if ($logo === '') {
        $logo = cx_brand_asset_path('watermark') ?: cx_brand_asset_path('logo_icon');
    }

    return [
        'enabled' => !empty($wm['enabled']),
        'burn_on_upload' => !empty($wm['burn_on_upload']),
        'logo' => $logo,
        'opacity_detail' => (float) ($wm['opacity_detail'] ?? 0.13),
        'opacity_card' => (float) ($wm['opacity_card'] ?? 0.11),
        'opacity_thumb' => (float) ($wm['opacity_thumb'] ?? 0.09),
        'blur_px' => (float) ($wm['blur_px'] ?? 0.6),
        'rotate_deg' => (float) ($wm['rotate_deg'] ?? -24),
    ];
}

/** @param array<string,scalar|null> $attrs */
function cx_photo_watermark_applies(string $context, array $attrs): bool
{
    if (array_key_exists('watermark', $attrs)) {
        return (bool) $attrs['watermark'];
    }
    $wm = cx_photo_watermark_config();
    if (!empty($wm['burn_on_upload'])) {
        return false;
    }
    if (!$wm['enabled'] || $wm['logo'] === '') {
        return false;
    }

    return in_array($context, ['card', 'detail', 'thumb', 'hero'], true);
}

/** @param array<string,scalar|null> $attrs */
function cx_photo_watermark_wrap(string $imgHtml, string $context, array $attrs): string
{
    if ($imgHtml === '' || !cx_photo_watermark_applies($context, $attrs)) {
        return $imgHtml;
    }
    $wm = cx_photo_watermark_config();
    $opacity = match ($context) {
        'detail', 'hero' => $wm['opacity_detail'],
        'thumb' => $wm['opacity_thumb'],
        default => $wm['opacity_card'],
    };
    $style = '--photo-wm-opacity:' . max(0.04, min(0.35, $opacity))
        . ';--photo-wm-blur:' . max(0, min(3, $wm['blur_px'])) . 'px'
        . ';--photo-wm-rotate:' . $wm['rotate_deg'] . 'deg'
        . ';--photo-wm-logo:url(' . cx_e($wm['logo']) . ')';

    $extraClass = (string) ($attrs['watermark_class'] ?? '');
    unset($attrs['watermark'], $attrs['watermark_class']);

    return '<span class="photo-watermark photo-watermark--' . cx_e($context)
        . ($extraClass !== '' ? ' ' . cx_e($extraClass) : '')
        . '" style="' . $style . '">'
        . $imgHtml
        . '<span class="photo-watermark__overlay" aria-hidden="true"></span>'
        . '</span>';
}

/** @param array<string,scalar|null> $attrs */
function cx_photo_img(string $url, string $context = 'card', array $attrs = [], string $siteUrl = '', string $uploadsUrl = '/uploads'): string
{
    $url = cx_photo_original($url);
    if ($url === '') {
        return '';
    }
    if ($siteUrl === '') {
        $cfg = cx_app_config();
        $siteUrl = (string) ($cfg['url'] ?? '');
        $uploadsUrl = (string) ($cfg['uploads_url'] ?? '/uploads');
    }

    $watermarkAttrs = $attrs;
    $map = cx_photo_widths();
    $defaultW = $map[$context] ?? $map['card'];
    $src = cx_photo_sized($url, $defaultW, $siteUrl, $uploadsUrl);
    $srcset = cx_photo_srcset($url, array_values($map), $siteUrl, $uploadsUrl);
    $sizes = cx_photo_sizes_for($context);

    $class = (string) ($attrs['class'] ?? '');
    unset($attrs['class'], $attrs['watermark'], $attrs['watermark_class']);
    $alt = (string) ($attrs['alt'] ?? '');
    unset($attrs['alt']);
    $loading = (string) ($attrs['loading'] ?? 'lazy');
    unset($attrs['loading']);
    $decoding = (string) ($attrs['decoding'] ?? 'async');
    unset($attrs['decoding']);

    $extra = '';
    foreach ($attrs as $key => $value) {
        if ($value === null) {
            continue;
        }
        $extra .= ' ' . cx_e((string) $key) . '="' . cx_e((string) $value) . '"';
    }

    $imgHtml = '<img class="' . cx_e($class) . '" src="' . cx_e($src) . '" srcset="' . cx_e($srcset)
        . '" sizes="' . cx_e($sizes) . '" alt="' . cx_e($alt) . '" loading="' . cx_e($loading)
        . '" decoding="' . cx_e($decoding) . '"' . $extra . '>';

    return cx_photo_watermark_wrap($imgHtml, $context, $watermarkAttrs);
}

function cx_share_url(int $listingNo, string $siteUrl): string
{
    return rtrim($siteUrl, '/') . '/?ilan=' . $listingNo;
}

function cx_listing_share_url(int $listingId, string $siteUrl, bool $cacheBust = false): string
{
    $url = rtrim($siteUrl, '/') . '/listing.php?id=' . $listingId;
    if ($cacheBust) {
        $url .= '&v=' . date('Ymd');
    }

    return $url;
}

function cx_app_uses_https(array $appConfig): bool
{
    return str_starts_with(strtolower((string) ($appConfig['url'] ?? '')), 'https://');
}

/** HTTP og:image icin gecerli HTTPS vekil (WhatsApp zorunlulugu). */
function cx_weserv_og_proxy(string $absoluteHttpUrl): string
{
    $parts = parse_url($absoluteHttpUrl);
    if (!is_array($parts)) {
        return $absoluteHttpUrl;
    }
    $host = strtolower((string) ($parts['host'] ?? ''));
    if (!in_array($host, ['changex.mehmetfer.com.tr', 'www.changex.mehmetfer.com.tr'], true)) {
        return $absoluteHttpUrl;
    }
    $origin = ($parts['scheme'] ?? 'http') . '://' . $host . ($parts['path'] ?? '');
    if (!empty($parts['query'])) {
        $origin .= '?' . $parts['query'];
    }

    return 'https://images.weserv.nl/?url=' . rawurlencode($origin) . '&w=1200&h=630&fit=cover&output=jpg';
}

function cx_listing_og_image_public_url(string $imageUrl, array $appConfig): string
{
    $imageUrl = trim($imageUrl);
    if ($imageUrl === '') {
        return '';
    }
    if (str_starts_with($imageUrl, 'https://')) {
        return $imageUrl;
    }
    if (str_starts_with($imageUrl, 'http://') && !cx_app_uses_https($appConfig)) {
        return cx_weserv_og_proxy($imageUrl);
    }

    return $imageUrl;
}

function cx_listing_og_image_url(int $listingId, string $siteUrl): string
{
    return rtrim($siteUrl, '/') . '/share-og.php?id=' . $listingId;
}

/** @param array<string,mixed> $item @param array<string,mixed> $appConfig */
function cx_listing_og_image_url_for_item(array $item, array $appConfig): string
{
    require_once dirname(__DIR__) . '/Services/ShareOgImageService.php';
    try {
        $path = \App\Services\ShareOgImageService::ensure($item, $appConfig);

        return \App\Services\ShareOgImageService::publicUrl($path, $appConfig);
    } catch (Throwable $e) {
        return cx_listing_og_image_url((int) ($item['id'] ?? 0), (string) ($appConfig['url'] ?? ''));
    }
}

/** @return array<string,string> */
function cx_listing_open_graph(array $item, int $listingId, int $listingNo, array $appConfig, ?string $ogImageUrl = null): array
{
    $siteUrl = rtrim((string) ($appConfig['url'] ?? ''), '/');
    $headline = cx_share_card_headline($item);
    $panel = cx_share_card_panel_fields($item, $listingNo);
    $descParts = array_filter([
        $panel['price_display'],
        $panel['year_label'],
        $panel['location'],
    ]);
    $description = implode(' · ', $descParts);
    if ($description === '') {
        $description = trim((string) ($item['title'] ?? ''));
    }
    $imageUrl = cx_listing_og_image_public_url($ogImageUrl ?? cx_listing_og_image_url($listingId, $siteUrl), $appConfig);
    $pageUrl = cx_listing_share_url($listingId, $siteUrl);

    return [
        'og:type' => 'website',
        'og:site_name' => cx_site_name(),
        'og:title' => $headline,
        'og:description' => $description,
        'og:url' => $pageUrl,
        'og:image' => $imageUrl,
        'og:image:type' => 'image/jpeg',
        'og:image:width' => '1200',
        'og:image:height' => '630',
        'twitter:card' => 'summary_large_image',
        'twitter:title' => $headline,
        'twitter:description' => $description,
        'twitter:image' => $imageUrl,
    ];
}

function cx_whatsapp_share_text(array $item, int $listingId, int $listingNo, string $siteUrl): string
{
    $headline = cx_share_card_headline($item);
    $panel = cx_share_card_panel_fields($item, $listingNo);
    $line2 = trim($panel['price_display'] . ($panel['location'] !== '' ? ' · ' . $panel['location'] : ''));
    $url = cx_listing_share_url($listingId, $siteUrl, true);
    $lines = array_filter([
        $headline,
        $line2 !== '' ? $line2 : null,
        $url,
    ]);

    return implode("\n", $lines);
}

function cx_whatsapp_share_url(array $item, int $listingId, int $listingNo, string $siteUrl): string
{
    return 'https://wa.me/?text=' . rawurlencode(cx_whatsapp_share_text($item, $listingId, $listingNo, $siteUrl));
}

function cx_absolute_url(string $path, string $siteUrl): string
{
    $path = trim($path);
    if ($path === '') {
        return '';
    }
    if (preg_match('#^https?://#i', $path)) {
        return $path;
    }

    return rtrim($siteUrl, '/') . '/' . ltrim($path, '/');
}

/** Instagram kart basligi (marka + model veya ilan basligi). */
function cx_share_card_headline(array $item): string
{
    require_once __DIR__ . '/vehicle-brands.php';
    require_once __DIR__ . '/vehicle-models.php';
    $make = cx_listing_vehicle_make($item);
    $model = cx_listing_vehicle_model($item);
    if ($make !== '' && $model !== '') {
        return mb_strtoupper($make . ' ' . $model, 'UTF-8');
    }
    if ($make !== '') {
        return mb_strtoupper($make, 'UTF-8');
    }

    return mb_strtoupper(trim((string) ($item['title'] ?? 'İLAN')), 'UTF-8');
}

/** Instagram paylasim hashtag satiri. */
function cx_share_card_hashtags(array $item): string
{
    require_once __DIR__ . '/vehicle-brands.php';
    $tags = ['#BenimBazar', '#ArabaKKTC', '#KKTC', '#ArabaKibris', '#SatilikAraba', '#IkinciEl'];
    $make = cx_listing_vehicle_make($item);
    if ($make !== '') {
        $slug = preg_replace('/[^A-Za-z0-9]/', '', $make) ?? '';
        if ($slug !== '') {
            $tags[] = '#' . $slug;
        }
    }
    $loc = trim((string) ($item['location'] ?? ''));
    if ($loc !== '') {
        $locSlug = preg_replace('/[^A-Za-z0-9]/u', '', $loc) ?? '';
        if ($locSlug !== '') {
            $tags[] = '#' . $locSlug;
        }
    }

    return implode(' ', array_slice(array_unique($tags), 0, 10));
}

/** Instagram aciklama metni (panoya kopyalanir). */
function cx_share_card_caption(array $item, int $listingNo, string $siteUrl): string
{
    $headline = cx_share_card_headline($item);
    $specs = cx_listing_quick_specs($item);
    $specLine = implode(' · ', array_slice(array_map(static fn (array $s): string => (string) $s['value'], $specs), 0, 4));
    $price = cx_listing_price_line($item);
    $loc = cx_listing_location_line($item);
    $url = cx_share_url($listingNo, $siteUrl);
    $lines = array_filter([
        $headline,
        $specLine !== '' ? $specLine : null,
        trim($price . ($loc !== '' ? ' · ' . $loc : '')),
        '',
        cx_share_card_hashtags($item),
        '',
        'İlan: ' . $url,
    ], static fn (?string $l): bool => $l !== null);

    return implode("\n", $lines);
}

/** Kart uzerinde gosterilecek fiyat (KKTC tarzi STG / TL). */
function cx_share_card_price_display(array $item): string
{
    $fx = cx_listing_price_currency($item);
    if ($fx !== null) {
        $amount = number_format($fx['amount'], 0, ',', '.');
        return match ($fx['currency']) {
            'GBP' => $amount . ' STG',
            'EUR' => $amount . ' EUR',
            'TRY' => $amount . ' TL',
            default => $amount . ' ' . $fx['currency'],
        };
    }

    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE') {
        $price = $item['price_tl'] ?? null;
        if ($price !== null && $price !== '') {
            return number_format((float) $price, 0, ',', '.') . ' TL';
        }
        return 'FIYAT SORULUR';
    }

    return 'TAKAS';
}

/** @return array<string,string> */
function cx_share_card_panel_fields(array $item, int $listingNo): array
{
    $vehicle = cx_listing_attrs($item)['vehicle'] ?? [];
    if (!is_array($vehicle)) {
        $vehicle = [];
    }
    $year = isset($vehicle['year']) ? (int) $vehicle['year'] : 0;
    $fuel = mb_strtoupper(trim((string) ($vehicle['fuel'] ?? '')), 'UTF-8');
    $trans = mb_strtoupper(trim((string) ($vehicle['transmission'] ?? '')), 'UTF-8');
    $listingId = (int) ($item['id'] ?? 0);
    $ref = $listingId > 0 ? (string) $listingId : (string) max(0, $listingNo - (int) (cx_app_config()['listing_no_base'] ?? 1000000000));

    return [
        'year_label' => $year > 0 ? $year . ' MODEL' : '',
        'price_display' => mb_strtoupper(cx_share_card_price_display($item), 'UTF-8'),
        'fuel' => $fuel !== '' ? $fuel : '—',
        'transmission' => $trans !== '' ? $trans : '—',
        'location' => cx_listing_location_line($item),
        'listing_ref' => 'İLAN: ' . $ref,
    ];
}

function cx_admin_role_label(?array $user): string
{
    try {
        return \App\Services\UserAdminService::label((string) ($user['role'] ?? 'user'));
    } catch (Throwable $e) {
        return (string) ($user['role'] ?? 'user');
    }
}

function cx_is_staff(?array $user): bool
{
    if ($user === null) {
        return false;
    }
    return in_array($user['role'] ?? '', ['admin', 'superadmin', 'moderator'], true);
}

function cx_is_superadmin(?array $user): bool
{
    return ($user['role'] ?? '') === 'superadmin';
}

function cx_is_admin(?array $user): bool
{
    return in_array($user['role'] ?? '', ['admin', 'superadmin'], true);
}

/** Onayci moderasyon yapabilir; silme sadece admin+ */
function cx_can_moderate_listings(?array $user): bool
{
    return cx_is_staff($user);
}

function cx_can_cancel_listings(?array $user): bool
{
    return cx_is_admin($user);
}

/** Onayci, yonetici, superadmin */
function cx_require_staff(): array
{
    $user = cx_require_user();
    if (!cx_can_moderate_listings($user)) {
        cx_flash('error', 'Yönetim paneline erişim yetkiniz yok.');
        cx_redirect('/');
    }
    return $user;
}

function cx_is_production(): bool
{
    return (bool) (cx_app_config()['production'] ?? false);
}

function cx_messages_enabled(): bool
{
    return (bool) (cx_app_config()['messages_enabled'] ?? false);
}

function cx_listing_is_public(string $status): bool
{
    return in_array(strtoupper(trim($status)), ['APPROVED', 'ACTIVE'], true);
}

function cx_listing_is_sold(string $status): bool
{
    return strtoupper(trim($status)) === 'SOLD';
}

function cx_listing_ttl_days(): int
{
    return max(1, (int) (cx_app_config()['listing_ttl_days'] ?? 90));
}

/** @param array<string,mixed> $listing */
function cx_listing_days_live(array $listing): int
{
    $pub = (float) ($listing['published_at'] ?? $listing['created_at'] ?? 0);
    if ($pub <= 0) {
        return 0;
    }

    return max(0, (int) floor((microtime(true) - $pub) / 86400));
}

/** @param array<string,mixed> $listing */
function cx_listing_days_ago_label(array $listing): string
{
    $days = cx_listing_days_live($listing);
    if ($days <= 0) {
        return 'bugün';
    }
    if ($days === 1) {
        return '1 gün önce';
    }

    return $days . ' gün önce';
}

function cx_listing_message_count(int $listingId): int
{
    if ($listingId <= 0) {
        return 0;
    }
    try {
        $pdo = \App\Helpers\Database::pdo();
        $stmt = $pdo->prepare(
            'SELECT COUNT(*) FROM messages m
             INNER JOIN message_conversations c ON c.id = m.conversation_id
             WHERE c.listing_id = ?'
        );
        $stmt->execute([$listingId]);

        return (int) $stmt->fetchColumn();
    } catch (Throwable) {
        return 0;
    }
}

/** @param array<string,mixed> $listing */
function cx_listing_card_stats_line(array $listing): string
{
    $views = (int) ($listing['view_count'] ?? 0);
    $favs = (int) ($listing['favorite_count'] ?? 0);
    $ago = cx_listing_days_ago_label($listing);

    return '👁 ' . number_format($views, 0, ',', '.')
        . ' • ❤️ ' . number_format($favs, 0, ',', '.')
        . ' • 📅 ' . $ago;
}

/** @param array<string,mixed> $listing */
function cx_listing_status_emoji(string $status): string
{
    return match (strtoupper(trim($status))) {
        'APPROVED', 'ACTIVE' => '🟢',
        'PENDING_MODERATION', 'PENDING' => '🟡',
        'SOLD' => '🔴',
        'REJECTED' => '⛔',
        'CANCELLED' => '⚫',
        default => '⚪',
    };
}

/** @param array<string,mixed> $viewer */
function cx_can_view_listing(?array $viewer, array $listing): bool
{
    $status = strtoupper((string) ($listing['status'] ?? ''));
    if (cx_listing_is_public($status) || cx_listing_is_sold($status)) {
        return true;
    }
    if ($viewer === null) {
        return false;
    }
    if (cx_is_staff($viewer)) {
        return true;
    }

    return (int) ($listing['owner_id'] ?? 0) === (int) ($viewer['id'] ?? 0);
}

/** @param array<string,mixed> $listing */
function cx_can_favorite_listing(array $listing): bool
{
    $status = strtoupper((string) ($listing['status'] ?? ''));

    return cx_listing_is_public($status);
}

/** @return list<string> */
function cx_staff_allowed_statuses(?array $actor): array
{
    if ($actor === null || !cx_can_moderate_listings($actor)) {
        return [];
    }
    $statuses = ['PENDING_MODERATION', 'PENDING', 'APPROVED', 'ACTIVE', 'REJECTED', 'SOLD'];
    if (cx_can_cancel_listings($actor)) {
        $statuses[] = 'CANCELLED';
    }

    return $statuses;
}

function cx_assert_staff_may_set_status(?array $actor, string $newStatus): void
{
    $newStatus = strtoupper(trim($newStatus));
    if (!in_array($newStatus, cx_staff_allowed_statuses($actor), true)) {
        throw new RuntimeException('Bu durum degisikligi icin yetkiniz yok.');
    }
}

/** @param array<string,mixed> $detail */
function cx_audit_log(int $actorId, string $action, string $entity, int $entityId, array $detail = []): void
{
    try {
        \App\Helpers\Database::pdo()->prepare(
            'INSERT INTO audit_logs (actor_id, action, entity, entity_id, detail, created_at)
             VALUES (?,?,?,?,?,?)'
        )->execute([
            $actorId,
            $action,
            $entity,
            $entityId,
            json_encode($detail, JSON_UNESCAPED_UNICODE),
            microtime(true),
        ]);
    } catch (Throwable) {
        // audit_logs tablosu yoksa devam
    }
}

/** Kurulum arayuzu anahtari — config/setup.local.php (git disi). */
function cx_setup_key(): ?string
{
    $path = BASE_PATH . '/config/setup.local.php';
    if (!is_file($path)) {
        return null;
    }
    /** @var array<string,mixed> $cfg */
    $cfg = require $path;
    $key = (string) ($cfg['setup_key'] ?? '');

    return $key !== '' ? $key : null;
}

function cx_verify_setup_key(string $key): bool
{
    $expected = cx_setup_key();
    if ($expected === null) {
        return false;
    }

    return hash_equals($expected, $key);
}

/** Production'da bilinen zayif sifrelerle giris engeli (config: block_weak_superadmin_password). */
function cx_is_blocked_password(string $username, string $password): bool
{
    if (!cx_is_production()) {
        return false;
    }
    $cfg = cx_app_config();
    if (empty($cfg['block_weak_superadmin_password'])) {
        return false;
    }
    $blocked = ['14531453', 'admin', 'password', '123456', 'superadmin'];
    if ($username === 'superadmin' && in_array($password, $blocked, true)) {
        return true;
    }

    return false;
}

/** Favori toggle — POST + CSRF (GET CSRF acigini kapatir). */
function cx_favorite_toggle_form(int $listingId, string $back, bool $isFav = false, string $extraClass = ''): string
{
    $back = cx_safe_next($back);
    $cls = trim('favorite-toggle-form ' . $extraClass);
    $btnCls = 'favorite-toggle-btn' . ($isFav ? ' is-on' : '');

    return '<form method="post" action="/favorite-toggle.php" class="' . cx_e($cls) . '">'
        . cx_csrf_field()
        . '<input type="hidden" name="id" value="' . $listingId . '">'
        . '<input type="hidden" name="back" value="' . cx_e($back) . '">'
        . '<button type="submit" class="' . cx_e($btnCls) . '" title="Favori" aria-label="Favori">♥</button>'
        . '</form>';
}

function cx_listing_status_label(string $status): string
{
    return match (strtoupper(trim($status))) {
        'PENDING_MODERATION', 'PENDING' => 'Onay Bekliyor',
        'APPROVED' => 'Onaylı',
        'ACTIVE' => 'Yayında',
        'SOLD' => 'Satıldı',
        'REJECTED' => 'Reddedildi',
        'CANCELLED' => 'Silindi',
        default => $status,
    };
}

function cx_listing_status_class(string $status): string
{
    return match (strtoupper(trim($status))) {
        'PENDING_MODERATION', 'PENDING' => 'is-pending',
        'APPROVED', 'ACTIVE' => 'is-approved',
        'SOLD' => 'is-sold',
        'REJECTED' => 'is-rejected',
        'CANCELLED' => 'is-cancelled',
        default => '',
    };
}

/** @param array<string,mixed> $item */
function cx_listing_no_display(array $item, int $base = 1000000000): int
{
    return (int) ($item['listing_no'] ?? cx_listing_no((int) $item['id'], $base));
}

/** @param array<string,mixed> $item */
function cx_listing_trade_label(array $item): string
{
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE') {
        $price = $item['price_tl'] ?? null;
        if ($price !== null && $price !== '') {
            return 'SATILIK · ' . number_format((float) $price, 0, ',', '.') . ' TL';
        }
        return 'SATILIK';
    }
    $wanted = trim((string) ($item['wanted_items'] ?? ''));
    if ($wanted !== '') {
        return 'TAKAS: ' . mb_strtoupper(mb_substr($wanted, 0, 48));
    }
    return 'TAKAS AÇIK';
}

function cx_is_dealer(?array $user): bool
{
    return ($user['role'] ?? '') === 'dealer';
}

function cx_is_vip_kurumsal(?array $user): bool
{
    return ($user['role'] ?? '') === 'vip_kurumsal';
}

/**
 * YYYY-MM-DD veya datetime → d.m.Y (TR). Boşsa boş string.
 */
function cx_format_tr_date(mixed $value): string
{
    $raw = trim((string) ($value ?? ''));
    if ($raw === '' || $raw === '0000-00-00' || str_starts_with($raw, '0000-00-00')) {
        return '';
    }
    $ts = strtotime(substr($raw, 0, 10));
    if ($ts === false) {
        return '';
    }

    return date('d.m.Y', $ts);
}

/**
 * HTML date input / form değeri için YYYY-MM-DD.
 */
function cx_ymd_date(mixed $value): string
{
    $raw = trim((string) ($value ?? ''));
    if ($raw === '' || $raw === '0000-00-00' || str_starts_with($raw, '0000-00-00')) {
        return '';
    }
    $ymd = substr($raw, 0, 10);
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $ymd)) {
        return '';
    }

    return $ymd;
}

/** Telefonu sadece rakamlara indirger. */
function cx_phone_digits(string $phone): string
{
    return preg_replace('/\D+/', '', $phone) ?? '';
}

/**
 * TR / KKTC karşılaştırması için son 10 hane (ülke kodu farklarını yok sayar).
 */
function cx_phone_match_key(string $phone): string
{
    $digits = cx_phone_digits($phone);
    if ($digits === '') {
        return '';
    }
    if (strlen($digits) >= 10) {
        return substr($digits, -10);
    }

    return $digits;
}

/**
 * VIP üyelik özeti (panel / admin).
 *
 * @return array{starts:string,ends:string,starts_ymd:string,ends_ymd:string,has_dates:bool,expired:bool,active:bool,status_label:string}
 */
function cx_vip_membership_summary(?array $user): array
{
    $startsYmd = cx_ymd_date($user['vip_starts_at'] ?? null);
    $endsYmd = cx_ymd_date($user['vip_ends_at'] ?? null);
    $today = date('Y-m-d');
    $hasDates = $startsYmd !== '' || $endsYmd !== '';
    $expired = $endsYmd !== '' && $endsYmd < $today;
    $notStarted = $startsYmd !== '' && $startsYmd > $today;
    $active = $hasDates && !$expired && !$notStarted;
    if (!$hasDates) {
        $status = 'Tarih tanımlanmadı';
    } elseif ($expired) {
        $status = 'Süresi doldu';
    } elseif ($notStarted) {
        $status = 'Henüz başlamadı';
    } else {
        $status = 'Aktif';
    }

    return [
        'starts' => cx_format_tr_date($startsYmd),
        'ends' => cx_format_tr_date($endsYmd),
        'starts_ymd' => $startsYmd,
        'ends_ymd' => $endsYmd,
        'has_dates' => $hasDates,
        'expired' => $expired,
        'active' => $active,
        'status_label' => $status,
    ];
}

/**
 * VIP Kurumsal: bitiş tarihi geçmişse veya başlangıç henüz gelmediyse giriş yok.
 * Diğer roller her zaman true. Tarih tanımlı değilse giriş serbest (admin girene kadar).
 */
function cx_vip_can_login(?array $user): bool
{
    if ($user === null || !cx_is_vip_kurumsal($user)) {
        return true;
    }
    $summary = cx_vip_membership_summary($user);
    if ($summary['expired']) {
        return false;
    }
    if ($summary['starts_ymd'] !== '' && $summary['starts_ymd'] > date('Y-m-d')) {
        return false;
    }

    return true;
}

function cx_vip_login_block_message(?array $user): string
{
    $summary = cx_vip_membership_summary($user ?? []);
    if ($summary['expired']) {
        $ends = $summary['ends'] !== '' ? ' (bitiş: ' . $summary['ends'] . ')' : '';

        return 'VIP Kurumsal üyeliğinizin süresi dolmuş' . $ends
            . '. Yenileme için yönetim ile iletişime geçin.';
    }
    if ($summary['starts_ymd'] !== '' && $summary['starts_ymd'] > date('Y-m-d')) {
        return 'VIP Kurumsal üyeliğiniz henüz başlamadı (başlangıç: '
            . $summary['starts'] . ').';
    }

    return 'VIP Kurumsal hesabınıza giriş yapılamıyor.';
}

/** Kurumsal galeri veya VIP kurumsal. */
function cx_is_corporate(?array $user): bool
{
    return cx_is_dealer($user) || cx_is_vip_kurumsal($user);
}

/** Aktif (slot sayilan) ilan durumlari. */
function cx_listing_active_slot_statuses(): array
{
    return ['PENDING_MODERATION', 'PENDING', 'APPROVED', 'ACTIVE'];
}

/** Rol bazli aktif arac ilan limiti. Staff / VIP kurumsal sinirsiz (0 = unlimited). */
function cx_user_listing_limit(?array $user): int
{
    if ($user === null) {
        return 3;
    }
    if (cx_is_staff($user) || cx_is_vip_kurumsal($user)) {
        return 0;
    }
    if (cx_is_dealer($user)) {
        return 10;
    }

    return 3;
}

function cx_user_active_listing_count(int $ownerId): int
{
    $statuses = cx_listing_active_slot_statuses();
    $placeholders = implode(',', array_fill(0, count($statuses), '?'));
    $stmt = \App\Helpers\Database::pdo()->prepare(
        "SELECT COUNT(*) AS c FROM trade_listings
         WHERE owner_id = ?
           AND UPPER(COALESCE(status,'')) IN ($placeholders)"
    );
    $stmt->execute(array_merge([$ownerId], $statuses));
    $row = $stmt->fetch();

    return (int) ($row['c'] ?? 0);
}

/**
 * @return array{ok:bool,count:int,limit:int,remaining:int,message:string,contact_admin:bool}
 */
function cx_user_listing_quota(?array $user): array
{
    $limit = cx_user_listing_limit($user);
    $count = $user ? cx_user_active_listing_count((int) $user['id']) : 0;
    if ($limit === 0) {
        $vip = cx_is_vip_kurumsal($user);

        return [
            'ok' => true,
            'count' => $count,
            'limit' => 0,
            'remaining' => 999,
            'message' => $vip
                ? "VIP Kurumsal: sinirsiz ilan. Aktif ilan: {$count}."
                : '',
            'contact_admin' => false,
        ];
    }
    $remaining = max(0, $limit - $count);
    $isDealer = cx_is_dealer($user);
    $ok = $count < $limit;
    $contact = $isDealer && $count >= $limit;
    if ($ok) {
        $message = $isDealer
            ? "Kurumsal (galeri) hesabiniz: {$count}/{$limit} aktif ilan. Kalan: {$remaining}."
            : "Uye hesabiniz: {$count}/{$limit} aktif arac ilani. Kalan: {$remaining}.";
    } elseif ($contact) {
        $message = "Kurumsal hesapta en fazla {$limit} aktif ilan olabilir. Sinirsiz ilan icin admin'den VIP Kurumsal talep edin.";
    } else {
        $message = "En fazla {$limit} aktif arac ilani verebilirsiniz. Mevcut aktif ilan: {$count}. Yeni ilan icin once bir ilani satildi/iptal edin veya galeri (kurumsal) hesabi isteyin.";
    }

    return [
        'ok' => $ok,
        'count' => $count,
        'limit' => $limit,
        'remaining' => $remaining,
        'message' => $message,
        'contact_admin' => $contact,
    ];
}

function cx_admin_contact_href(): string
{
    $app = cx_app_config();
    $mail = trim((string) ($app['admin_email'] ?? $app['contact_email'] ?? ''));
    if ($mail !== '' && filter_var($mail, FILTER_VALIDATE_EMAIL)) {
        return 'mailto:' . $mail . '?subject=' . rawurlencode('BenimBazar — ilan limiti artirimi');
    }

    return '/notifications.php';
}

function cx_listing_price_currency(array $item): ?array
{
    $attrs = cx_listing_attrs($item);
    $p = $attrs['price'] ?? null;
    if (!is_array($p)) {
        return null;
    }
    $cur = strtoupper(trim((string) ($p['currency'] ?? '')));
    $amount = $p['amount'] ?? null;
    if ($cur === '' || $amount === null || $amount === '') {
        return null;
    }

    return ['currency' => $cur, 'amount' => (float) $amount];
}

/** Ilan karti fiyat satiri (TL, GBP veya Takas). */
function cx_listing_price_line(array $item): string
{
    if (cx_listing_is_sold((string) ($item['status'] ?? ''))) {
        return 'SATILDI';
    }

    $fx = cx_listing_price_currency($item);
    if ($fx !== null) {
        if ($fx['currency'] === 'GBP') {
            return number_format($fx['amount'], 0, ',', '.') . ' £';
        }
        if ($fx['currency'] === 'EUR') {
            return number_format($fx['amount'], 0, ',', '.') . ' €';
        }
        if ($fx['currency'] === 'TRY') {
            return number_format($fx['amount'], 0, ',', '.') . ' ₺';
        }
    }

    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE') {
        $price = $item['price_tl'] ?? null;
        if ($price !== null && $price !== '') {
            return number_format((float) $price, 0, ',', '.') . ' TL';
        }
        return 'Fiyat sorulur';
    }
    return 'Takas';
}

/** Turkce kisa tarih: 14 Ağu 2026 */
function cx_listing_date_short(array $item): string
{
    $months = [
        1 => 'Oca', 2 => 'Şub', 3 => 'Mar', 4 => 'Nis', 5 => 'May', 6 => 'Haz',
        7 => 'Tem', 8 => 'Ağu', 9 => 'Eyl', 10 => 'Eki', 11 => 'Kas', 12 => 'Ara',
    ];
    $ts = (float) ($item['created_at'] ?? 0);
    if ($ts <= 0) {
        return '';
    }
    $day = (int) date('j', (int) $ts);
    $mon = (int) date('n', (int) $ts);
    $year = date('Y', (int) $ts);
    return $day . ' ' . ($months[$mon] ?? '') . ' ' . $year;
}

/** Turkce konum satiri (buyuk harf). */
function cx_listing_location_line(array $item): string
{
    $loc = trim((string) ($item['location'] ?? ''));
    if ($loc === '') {
        return 'Türkiye';
    }
    return mb_strtoupper($loc, 'UTF-8');
}

/** Bolge filtresi: kktc | all | '' (bos = kullanici ulkesine gore) */
function cx_normalize_country(string $country): string
{
    $c = strtolower(trim($country));
    return $c === 'kktc' ? 'kktc' : 'tr';
}

function cx_user_country(?array $user): string
{
    if ($user === null) {
        return 'tr';
    }

    return cx_normalize_country((string) ($user['country'] ?? 'tr'));
}

function cx_user_is_kktc(?array $user): bool
{
    return cx_user_country($user) === 'kktc';
}

/** Bolge filtresi: kktc | '' (filtre yok) */
function cx_region_from_request(?array $user = null): string
{
    $raw = strtolower(trim((string) ($_GET['region'] ?? '')));
    if ($raw === 'kktc') {
        return 'kktc';
    }
    if ($raw === 'all' || $raw === 'tr') {
        return '';
    }
    // Parametre yoksa: KKTC kullanicisina varsayilan KKTC filtresi
    if (!array_key_exists('region', $_GET) && cx_user_is_kktc($user)) {
        return 'kktc';
    }

    return '';
}

/** @return list<string> */
function cx_kktc_location_needles(): array
{
    return [
        'girne',
        'magosa',
        'mağusa',
        'magusa',
        'famagusta',
        'kıbrıs',
        'kibris',
        'cyprus',
        'kktc',
        'lefkoşa',
        'lefkosa',
        'nicosia',
        'güzelyurt',
        'guzelyurt',
        'iskele',
        'karpaz',
        'alsancak',
        'çatalköy',
        'catalkoy',
        'karaoğlanoğlu',
        'karaoglanoglu',
        'lapta',
        'gazimağusa',
        'gazimagusa',
    ];
}

/**
 * KKTC: Kıbrıs/Girne/Mağusa konumları VEYA sterlin (GBP) fiyat.
 * @return array{0:string,1:list<mixed>}
 */
function cx_region_sql(string $region, string $alias = 'l'): array
{
    if ($region !== 'kktc') {
        return ['', []];
    }

    $parts = [];
    $args = [];
    foreach (cx_kktc_location_needles() as $needle) {
        $parts[] = "LOWER({$alias}.location) LIKE ?";
        $args[] = '%' . mb_strtolower($needle, 'UTF-8') . '%';
    }
    // attrs_json icinde currency GBP / STG
    $parts[] = "UPPER(COALESCE({$alias}.attrs_json,'')) LIKE ?";
    $args[] = '%"CURRENCY":"GBP"%';
    $parts[] = "UPPER(COALESCE({$alias}.attrs_json,'')) LIKE ?";
    $args[] = '%"CURRENCY": "GBP"%';
    $parts[] = "UPPER(COALESCE({$alias}.attrs_json,'')) LIKE ?";
    $args[] = '%"CURRENCY":"STG"%';

    return [' AND (' . implode(' OR ', $parts) . ')', $args];
}

/** Ilan durumu (Turkce). */
function cx_condition_label(string $condition): string
{
    return match (strtolower(trim($condition))) {
        'new', 'sifir' => 'Sıfır',
        'like_new', 'like-new' => 'Sıfıra yakın',
        'fair', 'orta' => 'Orta',
        'good', 'iyi' => 'İyi durumda',
        default => $condition !== '' ? ucfirst($condition) : 'İyi durumda',
    };
}

/** Ilan alt baslik (kategori + mod). */
function cx_listing_subtitle(array $item): string
{
    $parts = array_filter([
        trim((string) ($item['subcategory'] ?? '')),
        trim((string) ($item['category'] ?? '')),
    ]);
    $parts = array_values(array_unique($parts));
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE') {
        $parts[] = 'Satılık';
    } else {
        $parts[] = 'Takas';
    }
    return implode(' · ', $parts);
}

/** Ozellik rozetleri (detay grid). */
function cx_listing_feature_tags(array $item): array
{
    $tags = [];
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode === 'TRADE') {
        $tags[] = ['icon' => '⇄', 'label' => 'Takas'];
    } else {
        $tags[] = ['icon' => '₺', 'label' => 'Satılık'];
        if (!empty($item['price_negotiable'])) {
            $tags[] = ['icon' => '💬', 'label' => 'Pazarlık yapılır'];
        }
    }
    $tags[] = ['icon' => '📦', 'label' => cx_condition_label((string) ($item['condition'] ?? 'good'))];
    $cat = trim((string) ($item['category'] ?? ''));
    $sub = trim((string) ($item['subcategory'] ?? ''));
    if ($sub !== '') {
        $tags[] = ['icon' => '🏷️', 'label' => $sub];
    } elseif ($cat !== '') {
        $tags[] = ['icon' => '🏷️', 'label' => $cat];
    }
    $wanted = trim((string) ($item['wanted_items'] ?? ''));
    if ($wanted !== '' && $mode === 'TRADE') {
        $tags[] = ['icon' => '🎯', 'label' => mb_strimwidth($wanted, 0, 28, '…')];
    }
    $score = (int) round((float) ($item['change_score'] ?? 0));
    if ($score >= 70) {
        $tags[] = ['icon' => '✓', 'label' => 'Doğrulanmış üye'];
    }
    $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]');
    if (count($photos) > 1) {
        $tags[] = ['icon' => '📷', 'label' => count($photos) . ' fotoğraf'];
    }
    return $tags;
}

/** @return array<string,mixed> */
function cx_listing_attrs(array $item): array
{
    $raw = $item['attrs_json'] ?? null;
    if ($raw === null || $raw === '') {
        return [];
    }
    $data = json_decode((string) $raw, true);
    return is_array($data) ? $data : [];
}

function cx_is_vehicle_listing(array $item): bool
{
    $attrs = cx_listing_attrs($item);
    if (!empty($attrs['vehicle']) && is_array($attrs['vehicle'])) {
        return true;
    }
    $sub = trim((string) ($item['subcategory'] ?? ''));
    if ($sub !== '' && cx_marketplace_by_label($sub) !== null) {
        return true;
    }
    $hay = mb_strtolower(implode(' ', array_filter([
        (string) ($item['title'] ?? ''),
        (string) ($item['subcategory'] ?? ''),
        (string) ($item['category'] ?? ''),
    ])));
    foreach (['bmw', 'mercedes', 'audi', 'otomobil', 'motosiklet', 'bisiklet', 'ticari', 'antika', 'araba', 'suv', 'sedan'] as $kw) {
        if (str_contains($hay, $kw)) {
            return true;
        }
    }
    return false;
}

/** Car.gr tarzi hizli arac ozellikleri (model yili, km, yakit...). */
function cx_listing_quick_specs(array $item): array
{
    $v = cx_listing_attrs($item)['vehicle'] ?? [];
    if (!is_array($v)) {
        $v = [];
    }
    $defs = [
        ['key' => 'year', 'label' => 'Model yılı', 'icon' => '📅'],
        ['key' => 'km', 'label' => 'Kilometre', 'icon' => '🛣️'],
        ['key' => 'fuel', 'label' => 'Yakıt', 'icon' => '⛽'],
        ['key' => 'engine_cc', 'label' => 'Motor hacmi', 'icon' => '⚙️'],
        ['key' => 'hp', 'label' => 'Beygir', 'icon' => '🐎'],
        ['key' => 'doors', 'label' => 'Kapı', 'icon' => '🚪'],
        ['key' => 'transmission', 'label' => 'Vites', 'icon' => '🔀'],
        ['key' => 'body', 'label' => 'Kasa', 'icon' => '🚗'],
        ['key' => 'drive', 'label' => 'Çekiş', 'icon' => '4️⃣'],
        ['key' => 'color', 'label' => 'Renk', 'icon' => '🎨'],
    ];
    $out = [];
    foreach ($defs as $def) {
        $val = $v[$def['key']] ?? null;
        if ($val === null || $val === '') {
            continue;
        }
        $display = match ($def['key']) {
            'km' => number_format((int) $val, 0, ',', '.') . ' km',
            'engine_cc' => number_format((int) $val, 0, ',', '.') . ' cc',
            'hp' => (string) $val . ' HP',
            default => (string) $val,
        };
        $out[] = ['icon' => $def['icon'], 'label' => $def['label'], 'value' => $display];
    }
    return $out;
}

/** @return list<string> */
function cx_listing_equipment(array $item): array
{
    $list = cx_listing_attrs($item)['equipment'] ?? [];
    if (!is_array($list)) {
        return [];
    }
    $out = [];
    foreach ($list as $row) {
        $s = trim((string) $row);
        if ($s !== '') {
            $out[] = $s;
        }
    }
    return $out;
}

/** @return array<string,mixed> */
function cx_listing_seller_meta(array $item): array
{
    $s = cx_listing_attrs($item)['seller'] ?? [];
    return is_array($s) ? $s : [];
}

/** Satıcı görünen adı (import: Caner Çakır vb.). */
function cx_listing_seller_display_name(array $item): string
{
    $meta = cx_listing_seller_meta($item);
    $name = trim((string) ($meta['display_name'] ?? ''));
    if ($name !== '') {
        return $name;
    }

    return trim((string) ($item['owner_username'] ?? 'Uye'));
}

function cx_owner_role_is_corporate(?string $role): bool
{
    return in_array((string) $role, ['dealer', 'vip_kurumsal'], true);
}

/** @return array{url:string,hint:string,is_corporate:bool} */
function cx_listing_seller_public_nav(array $item): array
{
    $ownerId = (int) ($item['owner_id'] ?? 0);
    $isCorporate = cx_owner_role_is_corporate((string) ($item['owner_role'] ?? ''));
    if (!$isCorporate) {
        $type = strtolower(trim((string) (cx_listing_seller_meta($item)['type'] ?? '')));
        if ($type !== '' && (str_contains($type, 'galeri') || str_contains($type, 'yetkili'))) {
            // İlan tipi galeri olsa bile hesap rolü kurumsal değilse üye sayfası
        }
    }

    return [
        'url' => $ownerId > 0
            ? ($isCorporate ? '/galeri.php?id=' . $ownerId : '/satici.php?id=' . $ownerId)
            : '',
        'hint' => $isCorporate ? 'Galerisine bak' : 'Kullanıcının diğer ilanlarını gör',
        'is_corporate' => $isCorporate,
    ];
}

/** Avatar / galeri logosu mutlak veya site-relatif URL. */
function cx_user_avatar_src(?string $raw, string $uploadsUrl = '/uploads'): string
{
    $raw = trim((string) $raw);
    if ($raw === '') {
        return '';
    }
    if (preg_match('#^https?://#i', $raw) || str_starts_with($raw, '//')) {
        return $raw;
    }
    $uploadsUrl = rtrim($uploadsUrl, '/');
    $stub = ltrim(str_replace('\\', '/', $raw), '/');
    if (str_starts_with($stub, 'uploads/')) {
        $stub = substr($stub, strlen('uploads/'));
    }

    return $uploadsUrl . '/' . $stub;
}

/**
 * Galeri logosu (filigransiz). Tek dosya; basariysa uploads stub doner.
 */
function cx_save_uploaded_gallery_logo(array $file, int $userId): ?string
{
    return cx_save_uploaded_gallery_image($file, $userId, 'gallery_logo');
}

/**
 * VIP vitrin / mağaza arka plan görseli (filigransız).
 */
function cx_save_uploaded_gallery_banner(array $file, int $userId): ?string
{
    return cx_save_uploaded_gallery_image($file, $userId, 'gallery_banner');
}

/** @param 'gallery_logo'|'gallery_banner' $prefix */
function cx_save_uploaded_gallery_image(array $file, int $userId, string $prefix): ?string
{
    if ((int) ($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
        return null;
    }
    $prefix = preg_replace('/[^a-z0-9_]/', '', $prefix) ?: 'gallery_img';
    $app = cx_app_config();
    $uploadDir = (string) ($app['uploads_path'] ?? (BASE_PATH . '/uploads'));
    if (!is_dir($uploadDir)) {
        @mkdir($uploadDir, 0755, true);
    }
    $maxBytes = (int) ($app['max_upload_bytes'] ?? 5242880);
    if ($prefix === 'gallery_banner') {
        $maxBytes = max($maxBytes, 8 * 1024 * 1024);
    }
    if ((int) ($file['size'] ?? 0) > $maxBytes) {
        return null;
    }
    $tmp = (string) ($file['tmp_name'] ?? '');
    $mime = (string) (@mime_content_type($tmp) ?: '');
    $allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!in_array($mime, $allowed, true)) {
        return null;
    }
    $ext = $mime === 'image/png' ? 'png' : ($mime === 'image/webp' ? 'webp' : 'jpg');
    $fname = $prefix . '_' . $userId . '_' . bin2hex(random_bytes(6)) . '.' . $ext;
    if (!@move_uploaded_file($tmp, $uploadDir . '/' . $fname)) {
        return null;
    }

    return $fname;
}

/** Satıcı alt satır: Bireysel Satıcı · Üye 2026 */
function cx_listing_seller_profile_line(array $item): string
{
    $meta = cx_listing_seller_meta($item);
    $line = trim((string) ($meta['profile_line'] ?? ''));
    if ($line !== '') {
        return $line;
    }
    $parts = array_filter([
        trim((string) ($meta['type_label'] ?? '')),
        !empty($meta['member_since']) ? 'Uye ' . trim((string) $meta['member_since']) : '',
        trim((string) ($meta['type'] ?? '')),
    ]);
    return implode(' · ', $parts);
}

/** Teknik tablo satirlari (Car.gr characteristics). */
function cx_listing_characteristics(array $item, int $no, bool $isSale): array
{
    $rows = [];
    $attrs = cx_listing_attrs($item);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $vehicleMap = [
        'make' => 'Marka',
        'model' => 'Model',
        'year' => 'Model yılı',
        'engine' => 'Motor',
        'km' => 'Kilometre',
        'fuel' => 'Yakıt tipi',
        'engine_cc' => 'Motor hacmi',
        'hp' => 'Beygir gücü',
        'doors' => 'Kapı sayısı',
        'transmission' => 'Vites',
        'body' => 'Kasa tipi',
        'drive' => 'Çekiş',
        'steering' => 'Direksiyon',
        'color' => 'Renk',
        'plate' => 'Plaka',
    ];
    foreach ($vehicleMap as $key => $label) {
        $val = $vehicle[$key] ?? null;
        if ($val === null || $val === '') {
            continue;
        }
        if ($key === 'km') {
            $val = number_format((int) $val, 0, ',', '.') . ' km';
        } elseif ($key === 'engine_cc') {
            $val = number_format((int) $val, 0, ',', '.') . ' cc';
        } elseif ($key === 'hp') {
            $val = (string) $val . ' HP';
        }
        $rows[] = ['label' => $label, 'value' => (string) $val];
    }
    $rows[] = ['label' => 'İlan no', 'value' => (string) $no];
    $sub = trim((string) ($item['subcategory'] ?? ''));
    $cat = trim((string) ($item['category'] ?? ''));
    if ($sub !== '') {
        $rows[] = ['label' => 'Kategori', 'value' => $sub];
        if ($cat !== '' && $cat !== $sub) {
            $rows[] = ['label' => 'Üst grup', 'value' => $cat];
        }
    } else {
        $rows[] = ['label' => 'Kategori', 'value' => $cat !== '' ? $cat : '—'];
    }
    $rows[] = ['label' => 'Durum', 'value' => cx_condition_label((string) ($item['condition'] ?? 'good'))];
    $rows[] = ['label' => 'Konum', 'value' => (string) ($item['location'] ?? '—')];
    $rows[] = ['label' => 'İlan türü', 'value' => $isSale ? 'Satılık' : 'Takas'];
    if ($isSale) {
        $rows[] = ['label' => 'Fiyat', 'value' => cx_listing_price_line($item)];
    }
    if ($d = cx_listing_date_short($item)) {
        $rows[] = ['label' => 'Yayın tarihi', 'value' => $d];
    }
    return $rows;
}

function cx_login_url(string $next, ?string $reason = null): string
{
    $q = ['next' => $next];
    if ($reason !== null && $reason !== '') {
        $q['reason'] = $reason;
    }
    return '/login.php?' . http_build_query($q);
}

function cx_safe_next(string $raw): string
{
    $raw = trim($raw);
    if ($raw === '' || !str_starts_with($raw, '/') || str_starts_with($raw, '//')) {
        return '/index.php';
    }
    return $raw;
}

/** FTP deploy bandi icin surum metni (version.php). */
function cx_deploy_marker(): ?string
{
    $path = BASE_PATH . '/version.php';
    if (!is_file($path)) {
        return null;
    }
    /** @var array<string,mixed> $v */
    $v = require $path;
    $time = trim((string) ($v['time'] ?? ''));
    $tag = trim((string) ($v['tag'] ?? ''));
    if ($time === '' && $tag === '') {
        return null;
    }
    return $tag !== '' ? ($tag . ' · ' . $time) : $time;
}

function cx_redirect(string $path): never
{
    header('Location: ' . $path);
    exit;
}

function cx_flash(string $key, ?string $value = null): ?string
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        @session_start();
    }
    if ($value !== null) {
        $_SESSION['_flash'][$key] = $value;
        return null;
    }
    $v = $_SESSION['_flash'][$key] ?? null;
    unset($_SESSION['_flash'][$key]);
    return is_string($v) ? $v : null;
}

function cx_csrf_field(): string
{
    return \App\Helpers\Security::csrfField();
}

function cx_google_enabled(): bool
{
    require_once BASE_PATH . '/app/Services/GoogleAuthService.php';
    return \App\Services\GoogleAuthService::config()['enabled'] ?? false;
}
