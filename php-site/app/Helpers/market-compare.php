<?php

declare(strict_types=1);

/** @return array{enabled:bool,min_samples:int,max_fetch:int,year_tolerance:int,avg_band_pct:float,segments:list<string>} */
function cx_market_compare_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['market_compare'] ?? null) ? $app['market_compare'] : [];
    $segments = $cfg['segments'] ?? ['otomobil', 'motosiklet', 'ticari', 'antika-arac'];
    if (!is_array($segments)) {
        $segments = ['otomobil', 'motosiklet', 'ticari', 'antika-arac'];
    }

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'min_samples' => max(3, min(12, (int) ($cfg['min_samples'] ?? 5))),
        'max_fetch' => max(60, min(400, (int) ($cfg['max_fetch'] ?? 250))),
        'year_tolerance' => max(0, min(3, (int) ($cfg['year_tolerance'] ?? 2))),
        'avg_band_pct' => max(3.0, min(20.0, (float) ($cfg['avg_band_pct'] ?? 5.0))),
        'segments' => array_values(array_filter(array_map('strval', $segments))),
    ];
}

function cx_market_compare_enabled(): bool
{
    return cx_market_compare_settings()['enabled'];
}

function cx_market_compare_transmission_key(string $transmission): string
{
    $v = mb_strtolower(trim($transmission), 'UTF-8');
    if ($v === '') {
        return '';
    }
    if (str_contains($v, 'otomatik') || str_contains($v, 'automatic')) {
        return 'automatic';
    }
    if (str_contains($v, 'manuel') || str_contains($v, 'manual')) {
        return 'manual';
    }
    if (str_contains($v, 'yarı') || str_contains($v, 'semi')) {
        return 'semi';
    }

    return $v;
}

function cx_market_compare_fuel_key(string $fuel): string
{
    $v = mb_strtolower(trim($fuel), 'UTF-8');
    if ($v === '') {
        return '';
    }
    if (str_contains($v, 'dizel') || str_contains($v, 'diesel')) {
        return 'diesel';
    }
    if (str_contains($v, 'hibrit') || str_contains($v, 'hybrid')) {
        return 'hybrid';
    }
    if (str_contains($v, 'elektr')) {
        return 'electric';
    }
    if (str_contains($v, 'lpg')) {
        return 'lpg';
    }
    if (str_contains($v, 'benzin') || str_contains($v, 'petrol') || str_contains($v, 'gasoline')) {
        return 'petrol';
    }

    return $v;
}

function cx_market_compare_body_key(string $body): string
{
    $v = mb_strtolower(trim($body), 'UTF-8');
    $v = str_replace(['-', '_'], ' ', $v);
    $v = preg_replace('/\s+/u', ' ', $v) ?? $v;

    return trim($v);
}

function cx_market_compare_location_key(string $location): string
{
    $raw = mb_strtolower(trim($location), 'UTF-8');
    if ($raw === '') {
        return '';
    }
    if (!function_exists('cx_kktc_cities')) {
        require_once __DIR__ . '/kktc-locations.php';
    }
    foreach (cx_kktc_cities() as $code => $info) {
        $needles = is_array($info['needles'] ?? null) ? $info['needles'] : [];
        foreach ($needles as $needle) {
            $n = mb_strtolower(trim((string) $needle), 'UTF-8');
            if ($n !== '' && str_contains($raw, $n)) {
                return (string) $code;
            }
        }
    }
    $clean = preg_replace('/[^\p{L}\p{N}\s]/u', ' ', $raw) ?? $raw;
    $parts = preg_split('/\s+/u', trim($clean)) ?: [];

    return (string) ($parts[0] ?? '');
}

/**
 * @param array<string,mixed> $attrs
 * @return array{
 *   segment:string,make:string,model:string,year:int,km:int,
 *   transmission:string,fuel:string,engine_cc:int,body:string,location:string
 * }|null
 */
function cx_market_compare_fingerprint(array $attrs): ?array
{
    $segment = trim((string) ($attrs['segment'] ?? ''));
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $make = trim((string) ($vehicle['make'] ?? ''));
    $model = trim((string) ($vehicle['model'] ?? ''));
    $year = isset($vehicle['year']) ? (int) $vehicle['year'] : 0;
    $km = isset($vehicle['km']) && $vehicle['km'] !== '' ? (int) $vehicle['km'] : -1;
    if ($segment === '' || $make === '' || $model === '' || $year < 1900) {
        return null;
    }

    $engineCc = 0;
    if (isset($vehicle['engine_cc']) && $vehicle['engine_cc'] !== '' && (int) $vehicle['engine_cc'] > 0) {
        $engineCc = (int) $vehicle['engine_cc'];
    }

    return [
        'segment' => $segment,
        'make' => $make,
        'model' => $model,
        'year' => $year,
        'km' => $km,
        'transmission' => cx_market_compare_transmission_key((string) ($vehicle['transmission'] ?? '')),
        'fuel' => cx_market_compare_fuel_key((string) ($vehicle['fuel'] ?? '')),
        'engine_cc' => $engineCc,
        'body' => cx_market_compare_body_key((string) ($vehicle['body'] ?? '')),
        'location' => cx_market_compare_location_key((string) ($attrs['_location'] ?? '')),
    ];
}

function cx_market_compare_optional_same(string $a, string $b): bool
{
    return $a === '' || $b === '' || $a === $b;
}

function cx_market_compare_km_ok(int $baseKm, int $otherKm, int $maxDelta): bool
{
    if ($baseKm < 0 || $otherKm < 0) {
        return true;
    }

    return abs($baseKm - $otherKm) <= $maxDelta;
}

function cx_market_compare_engine_ok(int $baseCc, int $otherCc, int $maxDelta): bool
{
    if ($baseCc <= 0 || $otherCc <= 0) {
        return true;
    }

    return abs($baseCc - $otherCc) <= $maxDelta;
}

/**
 * Marka + model zorunlu. Yıl, KM, yakıt, vites, motor, kasa, konum
 * varsa eşleşir; eksik alan uydurulmaz, yok sayılır.
 *
 * @param array<string,mixed> $base
 * @param array<string,mixed> $other
 */
function cx_market_compare_tier_match(string $tier, array $base, array $other, string $segment): bool
{
    if ($other['segment'] !== $base['segment']) {
        return false;
    }
    if (!cx_vehicle_make_equals($base['make'], $other['make'], $segment)) {
        return false;
    }
    if (cx_listing_similar_model_key($base['model']) !== cx_listing_similar_model_key($other['model'])) {
        return false;
    }

    $yearDiff = abs((int) $base['year'] - (int) $other['year']);
    $baseKm = (int) ($base['km'] ?? -1);
    $otherKm = (int) ($other['km'] ?? -1);
    $kmSpan = max($baseKm, $otherKm, 0);

    if ($tier === 'A') {
        $kmTol = max(10000, (int) round($kmSpan * 0.12));

        return $yearDiff === 0
            && cx_market_compare_km_ok($baseKm, $otherKm, $kmTol)
            && cx_market_compare_optional_same((string) $base['fuel'], (string) $other['fuel'])
            && cx_market_compare_optional_same((string) $base['transmission'], (string) $other['transmission'])
            && cx_market_compare_engine_ok((int) $base['engine_cc'], (int) $other['engine_cc'], 150)
            && cx_market_compare_optional_same((string) $base['body'], (string) $other['body'])
            && cx_market_compare_optional_same((string) $base['location'], (string) $other['location']);
    }

    if ($tier === 'B') {
        $kmTol = max(20000, (int) round($kmSpan * 0.25));

        return $yearDiff <= 1
            && cx_market_compare_km_ok($baseKm, $otherKm, $kmTol)
            && cx_market_compare_optional_same((string) $base['fuel'], (string) $other['fuel'])
            && cx_market_compare_optional_same((string) $base['transmission'], (string) $other['transmission'])
            && cx_market_compare_engine_ok((int) $base['engine_cc'], (int) $other['engine_cc'], 250)
            && cx_market_compare_optional_same((string) $base['body'], (string) $other['body']);
    }

    $kmTol = max(30000, (int) round($kmSpan * 0.40));

    return $yearDiff <= 2
        && cx_market_compare_km_ok($baseKm, $otherKm, $kmTol)
        && cx_market_compare_optional_same((string) $base['fuel'], (string) $other['fuel'])
        && cx_market_compare_optional_same((string) $base['transmission'], (string) $other['transmission']);
}

/** @param list<float> $prices */
function cx_market_compare_quantile(array $prices, float $q): float
{
    if ($prices === []) {
        return 0.0;
    }
    $sorted = $prices;
    sort($sorted, SORT_NUMERIC);
    $n = count($sorted);
    if ($n === 1) {
        return (float) $sorted[0];
    }
    $idx = ($n - 1) * max(0.0, min(1.0, $q));
    $lo = (int) floor($idx);
    $hi = (int) ceil($idx);
    if ($lo === $hi) {
        return (float) $sorted[$lo];
    }

    return (float) ($sorted[$lo] + ($sorted[$hi] - $sorted[$lo]) * ($idx - $lo));
}

/**
 * @param list<float> $prices
 * @return array{min:float,max:float,avg:float,median:float,p25:float,p75:float,count:int}
 */
function cx_market_compare_price_stats(array $prices): array
{
    if ($prices === []) {
        return [
            'min' => 0.0,
            'max' => 0.0,
            'avg' => 0.0,
            'median' => 0.0,
            'p25' => 0.0,
            'p75' => 0.0,
            'count' => 0,
        ];
    }

    $sorted = $prices;
    sort($sorted, SORT_NUMERIC);
    $sum = array_sum($sorted);

    return [
        'min' => (float) $sorted[0],
        'max' => (float) $sorted[count($sorted) - 1],
        'avg' => (float) ($sum / count($sorted)),
        'median' => cx_market_compare_quantile($sorted, 0.5),
        'p25' => cx_market_compare_quantile($sorted, 0.25),
        'p75' => cx_market_compare_quantile($sorted, 0.75),
        'count' => count($sorted),
    ];
}

function cx_market_compare_format_amount(float $amount, string $currency): string
{
    return cx_listing_price_format([
        'currency' => strtoupper($currency),
        'amount' => $amount,
    ]);
}

/** @param array<string,mixed> $attrs */
function cx_market_compare_context_label(array $attrs, string $tier = 'A'): string
{
    $fp = cx_market_compare_fingerprint($attrs);
    $vehicle = is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [];
    $parts = [];
    if ($fp !== null) {
        $make = cx_vehicle_canonical_make($fp['make'], $fp['segment']);
        if ($make !== '') {
            $parts[] = $make;
        }
        if ($fp['model'] !== '') {
            $parts[] = $fp['model'];
        }
        if ($fp['year'] >= 1900) {
            $parts[] = (string) $fp['year'];
        }
        if ($fp['km'] >= 0) {
            $parts[] = number_format($fp['km'], 0, ',', '.') . ' km';
        }
    }
    foreach (['fuel' => '', 'transmission' => '', 'engine_cc' => ' cc', 'body' => ''] as $key => $suffix) {
        $raw = $key === 'engine_cc'
            ? ((int) ($vehicle['engine_cc'] ?? 0) > 0 ? number_format((int) $vehicle['engine_cc'], 0, ',', '.') . $suffix : '')
            : trim((string) ($vehicle[$key] ?? ''));
        if ($raw !== '') {
            $parts[] = $raw;
        }
    }
    $loc = trim((string) ($attrs['_location'] ?? ''));
    if ($loc !== '') {
        $parts[] = $loc;
    }

    return implode(' · ', $parts);
}

/** @param array<string,mixed> $attrs */
function cx_market_compare_browse_url(array $attrs, string $tier): string
{
    $fp = cx_market_compare_fingerprint($attrs);
    if ($fp === null) {
        return '/index.php';
    }

    $segment = $fp['segment'];
    $make = cx_vehicle_canonical_make($fp['make'], $segment);
    $year = (int) $fp['year'];
    $yearTol = $tier === 'A' ? 0 : ($tier === 'B' ? 1 : 2);

    $params = [
        'veh' => $segment,
        'make[0]' => $make,
        'model' => $fp['model'],
    ];
    if ($year >= 1900) {
        $params['year_min'] = (string) max(1980, $year - $yearTol);
        $params['year_max'] = (string) ($year + $yearTol);
    }
    $fuel = trim((string) ((is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [])['fuel'] ?? ''));
    if ($fuel !== '') {
        $params['fuel[0]'] = $fuel;
    }
    $trans = trim((string) ((is_array($attrs['vehicle'] ?? null) ? $attrs['vehicle'] : [])['transmission'] ?? ''));
    if ($trans !== '') {
        $params['transmission[0]'] = $trans;
    }

    return '/index.php?' . http_build_query($params);
}

/**
 * @param array{min:float,max:float,avg:float,count:int} $stats
 * @return array{
 *   position:string,
 *   position_icon:string,
 *   position_label:string,
 *   avg_diff_pct:float,
 *   avg_diff_label:string
 * }
 */
function cx_market_compare_verdict(float $current, array $stats): array
{
    $cfg = cx_market_compare_settings();
    $band = $cfg['avg_band_pct'];
    $avg = (float) ($stats['avg'] ?? 0);
    $avgDiffPct = $avg > 0 ? (($avg - $current) / $avg) * 100 : 0.0;

    $position = 'normal';
    $positionIcon = '🟡';
    $positionLabel = 'Piyasa fiyatı';

    if ($avg > 0 && $avgDiffPct >= $band) {
        $position = 'below';
        $positionIcon = '🟢';
        $positionLabel = 'İyi fiyat';
    } elseif ($avg > 0 && $avgDiffPct <= -$band) {
        $position = 'above';
        $positionIcon = '🔴';
        $positionLabel = 'Yüksek fiyat';
    }

    $avgDiffLabel = '';
    $absDiff = abs($avgDiffPct);
    if ($avg > 0 && $absDiff >= 1.0) {
        $pct = max(1, (int) round($absDiff));
        $avgDiffLabel = $avgDiffPct > 0
            ? ('Bu araç benzer araçların ortalama fiyatından yaklaşık %' . $pct . ' daha düşük.')
            : ('Bu araç benzer araçların ortalama fiyatından yaklaşık %' . $pct . ' daha yüksek.');
    }

    return [
        'position' => $position,
        'position_icon' => $positionIcon,
        'position_label' => $positionLabel,
        'avg_diff_pct' => round($avgDiffPct, 1),
        'avg_diff_label' => $avgDiffLabel,
    ];
}

/** @return array<string,mixed> */
function cx_market_compare_insufficient(): array
{
    return [
        'ok' => false,
        'insufficient' => true,
        'count' => 0,
        'insufficient_label' => 'Bu araç için henüz yeterli piyasa verisi bulunamadı.',
    ];
}
