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
        return (int) $this->pdo->lastInsertId();
    }

    public function cancel(int $listingId, int $userId, bool $isStaff): bool
    {
        $stmt = $this->pdo->prepare('SELECT owner_id, status FROM trade_listings WHERE id = ?');
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
        $stmt = $this->pdo->prepare('SELECT owner_id, status FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $row = $stmt->fetch();
        if (!$row) {
            throw new \RuntimeException('Ilan bulunamadi.');
        }
        if ((int) $row['owner_id'] !== $userId) {
            throw new \RuntimeException('Bu ilani duzenleyemezsiniz.');
        }

        $oldStatus = strtoupper((string) ($row['status'] ?? ''));
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
    }
}
