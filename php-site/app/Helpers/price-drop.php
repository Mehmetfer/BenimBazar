<?php

declare(strict_types=1);

/** @return array{enabled:bool,dedup_seconds:int,email:bool} */
function cx_price_drop_alert_settings(): array
{
    $app = cx_app_config();
    $cfg = is_array($app['price_drop_alerts'] ?? null) ? $app['price_drop_alerts'] : [];

    return [
        'enabled' => !array_key_exists('enabled', $cfg) || !empty($cfg['enabled']),
        'dedup_seconds' => max(3600, (int) ($cfg['dedup_seconds'] ?? 86400)),
        'email' => !array_key_exists('email', $cfg) || !empty($cfg['email']),
    ];
}

function cx_price_drop_alerts_enabled(): bool
{
    return cx_price_drop_alert_settings()['enabled'];
}

/**
 * @param array<string,mixed> $item
 * @return array{currency:string,amount:float}|null
 */
function cx_listing_effective_price(array $item): ?array
{
    $fx = cx_listing_price_currency($item);
    if ($fx !== null && $fx['amount'] > 0) {
        return [
            'currency' => strtoupper($fx['currency']),
            'amount' => (float) $fx['amount'],
        ];
    }

    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    if ($mode !== 'SALE') {
        return null;
    }

    $price = $item['price_tl'] ?? null;
    if ($price !== null && $price !== '' && (float) $price > 0) {
        return [
            'currency' => 'TRY',
            'amount' => (float) $price,
        ];
    }

    return null;
}

/** @param array{currency:string,amount:float}|null $price */
function cx_listing_price_format(?array $price): string
{
    if ($price === null) {
        return 'Takas';
    }

    $amount = number_format($price['amount'], 0, ',', '.');
    $cur = $price['currency'];
    if ($cur === 'GBP') {
        return $amount . ' £';
    }
    if ($cur === 'EUR') {
        return $amount . ' €';
    }
    if ($cur === 'TRY') {
        return $amount . ' TL';
    }

    return $amount . ' ' . $cur;
}

/** @param array{currency:string,amount:float}|null $a @param array{currency:string,amount:float}|null $b */
function cx_listing_price_dropped(?array $a, ?array $b): bool
{
    if ($a === null || $b === null) {
        return false;
    }
    if ($a['currency'] !== $b['currency']) {
        return false;
    }

    return $b['amount'] < $a['amount'];
}

/** @param array{currency:string,amount:float}|null $a @param array{currency:string,amount:float}|null $b */
function cx_listing_price_rose(?array $a, ?array $b): bool
{
    if ($a === null || $b === null) {
        return false;
    }
    if ($a['currency'] !== $b['currency']) {
        return false;
    }

    return $b['amount'] > $a['amount'];
}

/** @param array<string,mixed> $item */
function cx_listing_photo_count(array $item): int
{
    return count(cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]'));
}

function cx_listing_price_step(float $amount, string $currency): int
{
    $cur = strtoupper($currency);
    if (in_array($cur, ['GBP', 'EUR'], true)) {
        if ($amount < 1000) {
            return 50;
        }
        if ($amount < 10000) {
            return 100;
        }
        if ($amount < 50000) {
            return 250;
        }

        return 500;
    }
    if ($amount < 50000) {
        return 1000;
    }
    if ($amount < 250000) {
        return 5000;
    }
    if ($amount < 1000000) {
        return 10000;
    }

    return 25000;
}

function cx_listing_can_adjust_price(array $item): bool
{
    $st = strtoupper((string) ($item['status'] ?? ''));
    if (in_array($st, ['CANCELLED', 'SOLD'], true)) {
        return false;
    }

    return strtoupper((string) ($item['listing_mode'] ?? '')) === 'SALE';
}

function cx_price_alert_toggle_form(int $listingId, string $back, bool $enabled, bool $isFav): string
{
    if (!$isFav || !cx_price_drop_alerts_enabled()) {
        return '';
    }

    $back = cx_safe_next($back);
    $cls = 'price-alert-toggle-form';
    $btnCls = 'price-alert-toggle-btn' . ($enabled ? ' is-on' : '');
    $label = $enabled ? 'Akıllı bildirimler açık' : 'Akıllı bildirimler kapalı';

    return '<form method="post" action="/alert-toggle.php" class="' . cx_e($cls) . '">'
        . cx_csrf_field()
        . '<input type="hidden" name="id" value="' . $listingId . '">'
        . '<input type="hidden" name="back" value="' . cx_e($back) . '">'
        . '<button type="submit" class="' . cx_e($btnCls) . '" title="' . cx_e($label) . '" aria-label="' . cx_e($label) . '">🔔</button>'
        . '</form>';
}
