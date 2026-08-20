<?php

declare(strict_types=1);

require_once __DIR__ . '/kktc-locations.php';

/** @return array{enabled:bool,min_photos:int,min_description_chars:int,min_title_chars:int,require_price_on_sale:bool,feed_require_vehicle_attrs:bool,feed_min_photos:int,min_score_submit:int} */
function cx_listing_quality_settings(): array
{
    $app = cx_app_config();
    $q = is_array($app['listing_quality'] ?? null) ? $app['listing_quality'] : [];

    return [
        'enabled' => !empty($q['enabled']),
        'min_photos' => max(1, min(20, (int) ($q['min_photos'] ?? 3))),
        'min_description_chars' => 10,
        'min_title_chars' => max(0, (int) ($q['min_title_chars'] ?? 10)),
        'require_price_on_sale' => !array_key_exists('require_price_on_sale', $q) || !empty($q['require_price_on_sale']),
        'feed_require_vehicle_attrs' => !array_key_exists('feed_require_vehicle_attrs', $q) || !empty($q['feed_require_vehicle_attrs']),
        'feed_min_photos' => max(0, (int) ($q['feed_min_photos'] ?? 1)),
        'min_score_submit' => max(0, min(100, (int) ($q['min_score_submit'] ?? 0))),
    ];
}

function cx_listing_quality_enabled(): bool
{
    return cx_listing_quality_settings()['enabled'];
}

function cx_listing_default_description(): string
{
    return 'İlgilenenler detaylı bilgi almak için iletişime geçebilir.';
}

function cx_listing_description_error(?string $desc): ?string
{
    $len = mb_strlen(trim((string) $desc), 'UTF-8');
    $min = cx_listing_quality_settings()['min_description_chars'];
    if ($len < $min) {
        return 'Açıklama en az ' . $min . ' karakter olmalı.';
    }

    return null;
}

/** @return list<string> */
function cx_listing_quality_vehicle_subcategories(): array
{
    $out = [];
    foreach (cx_marketplace_catalog() as $row) {
        $out[] = (string) $row['label'];
    }

    return $out;
}

/**
 * @param array<string,mixed> $input
 * @return array{score:int,issues:list<string>,checks:array<string,bool>}
 */
function cx_listing_quality_assess(array $input): array
{
    $cfg = cx_listing_quality_settings();
    $issues = [];
    $checks = [];

    $title = trim((string) ($input['title'] ?? ''));
    $desc = trim((string) ($input['description'] ?? ''));
    $mode = strtoupper(trim((string) ($input['listing_mode'] ?? 'TRADE')));
    $photos = $input['photo_urls'] ?? [];
    if (!is_array($photos)) {
        $photos = cx_photo_urls($photos);
    }
    $photoCount = count(array_filter($photos, static fn ($p) => trim((string) $p) !== ''));

    $checks['title'] = mb_strlen($title, 'UTF-8') >= $cfg['min_title_chars'];
    if (!$checks['title'] && $cfg['min_title_chars'] > 0) {
        $issues[] = 'Baslik en az ' . $cfg['min_title_chars'] . ' karakter olmali';
    }

    $checks['description'] = mb_strlen($desc, 'UTF-8') >= $cfg['min_description_chars'];
    if (!$checks['description'] && $cfg['min_description_chars'] > 0) {
        $issues[] = 'Aciklama en az ' . $cfg['min_description_chars'] . ' karakter olmali';
    }

    $checks['photos'] = $photoCount >= $cfg['min_photos'];
    if (!$checks['photos']) {
        $issues[] = 'En az ' . $cfg['min_photos'] . ' fotograf gerekli (' . $photoCount . ' yuklu)';
    }

    $hasPrice = cx_listing_quality_has_sale_price($input);
    $checks['price'] = $mode !== 'SALE' || !$cfg['require_price_on_sale'] || $hasPrice;
    if (!$checks['price']) {
        $issues[] = 'Satilik ilanlarda fiyat zorunlu';
    }

    $attrs = $input['attrs_json'] ?? null;
    if (!is_array($attrs) && is_string($attrs) && $attrs !== '') {
        $decoded = json_decode($attrs, true);
        $attrs = is_array($decoded) ? $decoded : null;
    }
    $vehicle = is_array($attrs) && is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $checks['vehicle_core'] = trim((string) ($vehicle['make'] ?? '')) !== ''
        && trim((string) ($vehicle['model'] ?? '')) !== ''
        && !empty($vehicle['year']);
    if (!$checks['vehicle_core']) {
        $issues[] = 'Marka, model ve model yili zorunlu';
    }

    $location = trim((string) ($input['location'] ?? ''));
    $userIsKktc = !empty($input['user_is_kktc']);
    $checks['location'] = true;
    if ($userIsKktc && $location !== '') {
        $validLabels = [];
        foreach (cx_kktc_cities() as $row) {
            $validLabels[] = (string) $row['label'];
        }
        $checks['location'] = in_array($location, $validLabels, true);
        if (!$checks['location']) {
            $issues[] = 'Gecerli bir KKTC sehri secin';
        }
    } elseif ($userIsKktc && $location === '') {
        $checks['location'] = false;
        $issues[] = 'Sehir secin';
    }

    $score = 0;
    if ($checks['photos']) {
        $score += min(25, 10 + (int) floor(min($photoCount, 6) / $cfg['min_photos'] * 15));
    }
    if ($checks['description']) {
        $score += 15;
    }
    if ($checks['title']) {
        $score += 10;
    }
    if ($checks['vehicle_core']) {
        $score += 25;
    }
    if ($checks['price']) {
        $score += 15;
    }
    if ($checks['location']) {
        $score += 5;
    }
    if (!empty($vehicle['km']) || (is_array($attrs) && ($attrs['segment'] ?? '') === 'bisiklet')) {
        $score += 5;
    }

    return [
        'score' => min(100, $score),
        'issues' => $issues,
        'checks' => $checks,
    ];
}

/** @param array<string,mixed> $input */
function cx_listing_quality_has_sale_price(array $input): bool
{
    $mode = strtoupper(trim((string) ($input['listing_mode'] ?? 'TRADE')));
    if ($mode !== 'SALE') {
        return true;
    }

    $priceTl = $input['price_tl'] ?? null;
    if ($priceTl !== null && $priceTl !== '' && (float) $priceTl > 0) {
        return true;
    }

    $amount = (float) ($input['price_amount'] ?? 0);
    if ($amount > 0) {
        return true;
    }

    $attrs = $input['attrs_json'] ?? null;
    if (!is_array($attrs) && is_string($attrs) && $attrs !== '') {
        $decoded = json_decode($attrs, true);
        $attrs = is_array($decoded) ? $decoded : null;
    }
    if (is_array($attrs) && is_array($attrs['price'] ?? null)) {
        $p = $attrs['price'];
        if ((float) ($p['amount'] ?? 0) > 0) {
            return true;
        }
    }

    return false;
}

/**
 * Sunucu tarafı gönderim doğrulaması — hata mesajı veya null.
 *
 * @param array<string,mixed> $input
 */
function cx_listing_quality_validate(array $input): ?string
{
    $descErr = cx_listing_description_error((string) ($input['description'] ?? ''));
    if ($descErr !== null) {
        return $descErr;
    }

    if (!cx_listing_quality_enabled()) {
        return null;
    }

    $assess = cx_listing_quality_assess($input);
    $cfg = cx_listing_quality_settings();

    if ($assess['issues'] !== []) {
        return $assess['issues'][0];
    }

    if ($cfg['min_score_submit'] > 0 && $assess['score'] < $cfg['min_score_submit']) {
        return 'Ilan kalite skoru yetersiz (' . $assess['score'] . '/100). Eksik alanlari tamamlayin.';
    }

    return null;
}

/** @param array<string,mixed> $item */
function cx_listing_passes_feed_quality(array $item): bool
{
    if (!cx_listing_quality_enabled()) {
        return true;
    }

    $cfg = cx_listing_quality_settings();
    if (!$cfg['feed_require_vehicle_attrs']) {
        return true;
    }

    if ((string) ($item['category'] ?? '') !== 'Araçlar') {
        return false;
    }

    $sub = trim((string) ($item['subcategory'] ?? ''));
    if (!in_array($sub, cx_listing_quality_vehicle_subcategories(), true)) {
        return false;
    }

    $attrs = cx_listing_attrs($item);
    if ($attrs === [] || trim((string) ($attrs['segment'] ?? '')) === '') {
        return false;
    }

    if ($cfg['feed_min_photos'] > 0) {
        $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]');
        if (count($photos) < $cfg['feed_min_photos']) {
            return false;
        }
    }

    return true;
}

/**
 * Admin kuyruk chip'leri.
 *
 * @param array<string,mixed> $row
 * @return list<string>
 */
function cx_listing_quality_admin_flags(array $row): array
{
    if (!cx_listing_quality_enabled()) {
        return [];
    }

    $cfg = cx_listing_quality_settings();
    $photos = cx_photo_urls($row['photo_urls'] ?? '[]');
    $flags = [];

    if (count($photos) < $cfg['min_photos']) {
        $flags[] = 'Foto<' . $cfg['min_photos'];
    }

    $desc = trim((string) ($row['description'] ?? ''));
    if (mb_strlen($desc, 'UTF-8') < $cfg['min_description_chars']) {
        $flags[] = 'Kisa aciklama';
    }

    $mode = strtoupper((string) ($row['listing_mode'] ?? 'TRADE'));
    if ($mode === 'SALE' && $cfg['require_price_on_sale'] && !cx_listing_quality_has_sale_price([
        'listing_mode' => $mode,
        'price_tl' => $row['price_tl'] ?? null,
        'attrs_json' => cx_listing_attrs($row),
    ])) {
        $flags[] = 'Fiyatsiz';
    }

    $attrs = cx_listing_attrs($row);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    if (trim((string) ($vehicle['make'] ?? '')) === '' || trim((string) ($vehicle['model'] ?? '')) === '') {
        $flags[] = 'Eksik arac';
    }

    if (!cx_listing_passes_feed_quality($row)) {
        $flags[] = 'Feed disi';
    }

    return $flags;
}

function cx_listing_quality_score_class(int $score): string
{
    if ($score >= 75) {
        return 'ok';
    }
    if ($score >= 50) {
        return 'warn';
    }

    return 'bad';
}
