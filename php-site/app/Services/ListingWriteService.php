<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Auth;
use App\Helpers\Database;
use PDO;

require_once __DIR__ . '/SocialService.php';

final class ListingWriteService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /** @param array<string,mixed> $data */
    public function create(int $ownerId, array $data): int
    {
        $userRow = null;
        try {
            $st = $this->pdo->prepare('SELECT id, role FROM users WHERE id = ? LIMIT 1');
            $st->execute([$ownerId]);
            $userRow = $st->fetch() ?: null;
        } catch (\Throwable) {
            $userRow = ['id' => $ownerId, 'role' => 'user'];
        }
        $quota = cx_user_listing_quota(is_array($userRow) ? $userRow : null);
        if (!$quota['ok']) {
            throw new \RuntimeException($quota['message']);
        }

        $now = microtime(true);
        $mode = strtoupper((string) ($data['listing_mode'] ?? 'TRADE'));
        $price = $mode === 'SALE' ? ($data['price_tl'] ?? null) : null;
        $photos = json_encode($data['photo_urls'] ?? [], JSON_UNESCAPED_UNICODE);
        $accept = json_encode($data['accept_categories'] ?? [], JSON_UNESCAPED_UNICODE);
        $attrsJson = null;
        if (!empty($data['attrs_json'])) {
            $attrsJson = is_string($data['attrs_json'])
                ? $data['attrs_json']
                : json_encode($data['attrs_json'], JSON_UNESCAPED_UNICODE);
        }

        $hasAttrs = false;
        try {
            $hasAttrs = (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
        } catch (\Throwable) {
            $hasAttrs = false;
        }

        if ($hasAttrs) {
            $this->pdo->prepare(
                'INSERT INTO trade_listings (
                  owner_id, title, description, category, subcategory, `condition`, location,
                  mandal_units, accept_categories, wanted_items, min_mandal_units, max_mandal_units,
                  photo_urls, attrs_json, status, listing_mode, price_tl, price_negotiable, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            )->execute([
                $ownerId,
                (string) ($data['title'] ?? ''),
                (string) ($data['description'] ?? ''),
                (string) ($data['category'] ?? 'Araçlar'),
                (string) ($data['subcategory'] ?? ''),
                (string) ($data['condition'] ?? 'good'),
                (string) ($data['location'] ?? ''),
                (int) ($data['mandal_units'] ?? 0),
                $accept ?: '[]',
                (string) ($data['wanted_items'] ?? ''),
                (int) ($data['min_mandal_units'] ?? 0),
                (int) ($data['max_mandal_units'] ?? 0),
                $photos ?: '[]',
                $attrsJson,
                'PENDING_MODERATION',
                $mode,
                $price,
                !empty($data['price_negotiable']) ? 1 : 0,
                $now,
                $now,
            ]);
        } else {
            $this->pdo->prepare(
                'INSERT INTO trade_listings (
                  owner_id, title, description, category, subcategory, `condition`, location,
                  mandal_units, accept_categories, wanted_items, min_mandal_units, max_mandal_units,
                  photo_urls, status, listing_mode, price_tl, price_negotiable, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            )->execute([
                $ownerId,
                (string) ($data['title'] ?? ''),
                (string) ($data['description'] ?? ''),
                (string) ($data['category'] ?? 'Araçlar'),
                (string) ($data['subcategory'] ?? ''),
                (string) ($data['condition'] ?? 'good'),
                (string) ($data['location'] ?? ''),
                (int) ($data['mandal_units'] ?? 0),
                $accept ?: '[]',
                (string) ($data['wanted_items'] ?? ''),
                (int) ($data['min_mandal_units'] ?? 0),
                (int) ($data['max_mandal_units'] ?? 0),
                $photos ?: '[]',
                'PENDING_MODERATION',
                $mode,
                $price,
                !empty($data['price_negotiable']) ? 1 : 0,
                $now,
                $now,
            ]);
        }
        $newId = (int) $this->pdo->lastInsertId();
        if ($newId > 0) {
            try {
                $seed = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
                $seed->execute([$newId]);
                $seedRow = $seed->fetch(PDO::FETCH_ASSOC);
                if (is_array($seedRow)) {
                    (new PriceHistoryService())->seedInitial($newId, $seedRow);
                }
            } catch (\Throwable) {
                // fiyat gecmisi opsiyonel
            }
        }

        return $newId;
    }

    public function cancel(int $listingId, int $userId, bool $isStaff): bool
    {
        $stmt = $this->pdo->prepare('SELECT owner_id, status, title FROM trade_listings WHERE id = ?');
        $stmt->execute([$listingId]);
        $row = $stmt->fetch();
        if (!$row) {
            return false;
        }
        if ((int) $row['owner_id'] !== $userId && !$isStaff) {
            return false;
        }
        if (strtoupper((string) $row['status']) === 'CANCELLED') {
            return true;
        }
        $this->pdo->prepare(
            'UPDATE trade_listings SET status = ?, updated_at = ? WHERE id = ?'
        )->execute(['CANCELLED', microtime(true), $listingId]);
        require_once __DIR__ . '/PriceDropAlertService.php';
        (new PriceDropAlertService())->notifyListingGone(
            $listingId,
            'removed',
            (string) ($row['title'] ?? ''),
            (int) $row['owner_id']
        );

        return true;
    }

    /** Sahip: satildi olarak isaretle. */
    public function markSold(int $listingId, int $userId): void
    {
        (new ListingLifecycleService())->markSold($listingId, $userId);
    }

    /** Sahip: suresi dolan ilani yeniden yayinla. */
    public function republish(int $listingId, int $userId): void
    {
        (new ListingLifecycleService())->requestRepublish($listingId, $userId);
    }

    /** @return list<array<string,mixed>> */
    public function mine(int $userId): array
    {
        $stmt = $this->pdo->prepare(
            'SELECT * FROM trade_listings WHERE owner_id = ? ORDER BY created_at DESC LIMIT 100'
        );
        $stmt->execute([$userId]);
        $rows = $stmt->fetchAll();
        $base = (int) (cx_app_config()['listing_no_base'] ?? 1000000000);
        foreach ($rows as &$row) {
            $row['listing_no'] = $base + (int) $row['id'];
            $row['view_count'] = (int) ($row['view_count'] ?? 0);
            $row['favorite_count'] = SocialService::favoriteCount((int) $row['id']);
            $row['days_live'] = cx_listing_days_live($row);
            $row['is_expired'] = ListingLifecycleService::isExpiredRow($row);
        }
        unset($row);

        return $rows;
    }

    /**
     * @param array<string,mixed> $data
     */
    public function updateForOwner(int $listingId, int $userId, array $data): void
    {
        $stmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $oldRow = $stmt->fetch();
        if (!$oldRow) {
            throw new \RuntimeException('Ilan bulunamadi.');
        }
        if ((int) $oldRow['owner_id'] !== $userId) {
            throw new \RuntimeException('Bu ilani duzenleyemezsiniz.');
        }

        $oldStatus = strtoupper((string) ($oldRow['status'] ?? ''));
        if ($oldStatus === 'CANCELLED' || $oldStatus === 'SOLD') {
            throw new \RuntimeException('Iptal edilmis veya satilmis ilan duzenlenemez.');
        }

        $newStatus = in_array($oldStatus, ['APPROVED', 'ACTIVE', 'REJECTED'], true)
            ? 'PENDING_MODERATION'
            : $oldStatus;

        $mode = strtoupper((string) ($data['listing_mode'] ?? 'TRADE'));
        $price = $mode === 'SALE' ? (float) ($data['price_tl'] ?? 0) : null;
        if ($mode === 'SALE' && ($price === null || $price <= 0)) {
            throw new \RuntimeException('Satilik ilan icin fiyat girin.');
        }

        $photos = $data['photo_urls'] ?? null;
        if ($photos === null) {
            $ex = $this->pdo->prepare('SELECT photo_urls FROM trade_listings WHERE id = ? LIMIT 1');
            $ex->execute([$listingId]);
            $photosJson = $ex->fetchColumn();
            $photos = json_decode(is_string($photosJson) ? $photosJson : '[]', true);
            if (!is_array($photos)) {
                $photos = [];
            }
        }

        $attrsJson = null;
        if (!empty($data['attrs_json'])) {
            $attrsJson = is_string($data['attrs_json'])
                ? $data['attrs_json']
                : json_encode($data['attrs_json'], JSON_UNESCAPED_UNICODE);
        }

        $hasAttrs = false;
        try {
            $hasAttrs = (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
        } catch (\Throwable) {
            $hasAttrs = false;
        }

        $now = microtime(true);
        $photosJson = json_encode($photos, JSON_UNESCAPED_UNICODE) ?: '[]';
        $base = [
            (string) ($data['title'] ?? ''),
            (string) ($data['description'] ?? ''),
            (string) ($data['category'] ?? ''),
            (string) ($data['subcategory'] ?? ''),
            (string) ($data['location'] ?? ''),
            (string) ($data['wanted_items'] ?? ''),
            $mode,
            $price,
            !empty($data['price_negotiable']) ? 1 : 0,
            $newStatus,
            $photosJson,
        ];

        if ($hasAttrs && $attrsJson !== null) {
            $this->pdo->prepare(
                'UPDATE trade_listings SET
                  title = ?, description = ?, category = ?, subcategory = ?, location = ?,
                  wanted_items = ?, listing_mode = ?, price_tl = ?, price_negotiable = ?,
                  status = ?, photo_urls = ?, attrs_json = ?, updated_at = ?
                 WHERE id = ? AND owner_id = ?'
            )->execute(array_merge($base, [$attrsJson, $now, $listingId, $userId]));
        } else {
            $this->pdo->prepare(
                'UPDATE trade_listings SET
                  title = ?, description = ?, category = ?, subcategory = ?, location = ?,
                  wanted_items = ?, listing_mode = ?, price_tl = ?, price_negotiable = ?,
                  status = ?, photo_urls = ?, updated_at = ?
                 WHERE id = ? AND owner_id = ?'
            )->execute(array_merge($base, [$now, $listingId, $userId]));
        }

        $newStmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $newStmt->execute([$listingId]);
        $newRow = $newStmt->fetch();
        if (is_array($newRow)) {
            require_once __DIR__ . '/PriceDropAlertService.php';
            (new PriceDropAlertService())->handleListingPriceChange($listingId, $oldRow, $newRow, true);
        }
    }

    /**
     * Sadece fiyatı değiştirir; ilan yayında kalır (moderasyona düşmez).
     *
     * @return array{old:array{currency:string,amount:float}|null,new:array{currency:string,amount:float}}
     */
    public function adjustPriceForOwner(int $listingId, int $userId, string $op, float $exactAmount = 0): array
    {
        require_once __DIR__ . '/../Helpers/price-drop.php';

        $stmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $oldRow = $stmt->fetch();
        if (!$oldRow) {
            throw new \RuntimeException('İlan bulunamadı.');
        }
        if ((int) $oldRow['owner_id'] !== $userId) {
            throw new \RuntimeException('Bu ilanın fiyatını değiştiremezsiniz.');
        }
        if (!cx_listing_can_adjust_price($oldRow)) {
            throw new \RuntimeException('Bu ilanda fiyat değiştirilemez.');
        }

        $oldPrice = cx_listing_effective_price($oldRow);
        $op = strtolower(trim($op));
        if (!in_array($op, ['up', 'down', 'set'], true)) {
            throw new \RuntimeException('Geçersiz fiyat işlemi.');
        }

        $max = 99999999.0;
        if ($op === 'set') {
            $amount = round($exactAmount);
            $currency = $oldPrice['currency'] ?? 'TRY';
        } else {
            if ($oldPrice === null) {
                throw new \RuntimeException('Önce bir fiyat girin.');
            }
            $currency = $oldPrice['currency'];
            $step = cx_listing_price_step($oldPrice['amount'], $currency);
            $amount = round($oldPrice['amount'] + ($op === 'up' ? $step : -$step));
        }

        if ($amount < 1) {
            throw new \RuntimeException('Fiyat 1’in altına inemez.');
        }
        if ($amount > $max) {
            throw new \RuntimeException('Fiyat çok yüksek.');
        }
        if ($oldPrice !== null && (int) round($oldPrice['amount']) === (int) $amount && $oldPrice['currency'] === $currency) {
            throw new \RuntimeException('Fiyat zaten bu tutarda.');
        }

        $attrs = cx_listing_attrs($oldRow);
        $hasFx = isset($attrs['price']) && is_array($attrs['price']);
        $priceTl = $oldRow['price_tl'] ?? null;

        if ($hasFx || in_array($currency, ['GBP', 'EUR'], true)) {
            $attrs['price'] = ['currency' => $currency, 'amount' => $amount];
            $priceTl = $currency === 'TRY' ? $amount : $priceTl;
        } else {
            $priceTl = $amount;
            if ($hasFx && strtoupper((string) ($attrs['price']['currency'] ?? '')) === 'TRY') {
                $attrs['price']['amount'] = $amount;
            }
        }

        $attrsJson = json_encode($attrs, JSON_UNESCAPED_UNICODE);
        $now = microtime(true);
        $hasAttrs = false;
        try {
            $hasAttrs = (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
        } catch (\Throwable) {
            $hasAttrs = false;
        }

        if ($hasAttrs) {
            $this->pdo->prepare(
                'UPDATE trade_listings SET price_tl = ?, attrs_json = ?, updated_at = ? WHERE id = ? AND owner_id = ?'
            )->execute([$priceTl, $attrsJson, $now, $listingId, $userId]);
        } else {
            $this->pdo->prepare(
                'UPDATE trade_listings SET price_tl = ?, updated_at = ? WHERE id = ? AND owner_id = ?'
            )->execute([$priceTl, $now, $listingId, $userId]);
        }

        $newStmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $newStmt->execute([$listingId]);
        $newRow = $newStmt->fetch();
        if (!is_array($newRow)) {
            throw new \RuntimeException('Fiyat kaydedilemedi.');
        }

        $newPrice = cx_listing_effective_price($newRow);
        if ($newPrice === null) {
            throw new \RuntimeException('Fiyat kaydedilemedi.');
        }

        require_once __DIR__ . '/PriceDropAlertService.php';
        $public = function_exists('cx_listing_is_public') && cx_listing_is_public((string) ($newRow['status'] ?? ''));
        (new PriceDropAlertService())->handleListingPriceChange($listingId, $oldRow, $newRow, !$public);

        return ['old' => $oldPrice, 'new' => $newPrice];
    }
}
