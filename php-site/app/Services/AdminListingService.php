<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

require_once __DIR__ . '/SocialService.php';
require_once __DIR__ . '/ListingSchemaService.php';

final class AdminListingService
{
    private PDO $pdo;
    private int $listingNoBase;
    private static ?string $lastListError = null;

    public function __construct()
    {
        $this->pdo = Database::pdo();
        $cfg = cx_app_config();
        $this->listingNoBase = (int) ($cfg['listing_no_base'] ?? 1000000000);
    }

    /** @return array{pending:int,approved:int,rejected:int,total:int,published:int,approved_only:int,active_only:int,cancelled:int,site_feed_limit:int} */
    public function stats(): array
    {
        $empty = [
            'pending' => 0,
            'approved' => 0,
            'approved_only' => 0,
            'active_only' => 0,
            'published' => 0,
            'rejected' => 0,
            'cancelled' => 0,
            'total' => 0,
            'site_feed_limit' => 500,
        ];
        try {
            $rows = $this->pdo->query(
                "SELECT UPPER(COALESCE(status,'')) AS st, COUNT(*) AS c
                 FROM trade_listings GROUP BY UPPER(COALESCE(status,''))"
            )->fetchAll();
        } catch (\Throwable) {
            return $empty;
        }
        $out = $empty;
        foreach ($rows as $r) {
            $c = (int) $r['c'];
            $out['total'] += $c;
            $st = (string) $r['st'];
            if (in_array($st, ['PENDING_MODERATION', 'PENDING'], true)) {
                $out['pending'] += $c;
            } elseif ($st === 'APPROVED') {
                $out['approved_only'] += $c;
                $out['approved'] += $c;
                $out['published'] += $c;
            } elseif ($st === 'ACTIVE') {
                $out['active_only'] += $c;
                $out['approved'] += $c;
                $out['published'] += $c;
            } elseif ($st === 'REJECTED') {
                $out['rejected'] += $c;
            } elseif ($st === 'CANCELLED') {
                $out['cancelled'] += $c;
            }
        }

        return $out;
    }

    /** Yayindaki tum ilanlari tek duruma (ACTIVE) ceker — admin sayaci = site. */
    public function syncPublishedToActiveSystem(): int
    {
        $stmt = $this->pdo->prepare(
            "UPDATE trade_listings SET status = 'ACTIVE', updated_at = ?
             WHERE UPPER(COALESCE(status, '')) IN ('APPROVED', 'ACTIVE')"
        );
        $stmt->execute([microtime(true)]);

        return $stmt->rowCount();
    }

    public function syncPublishedToActive(array $actor): int
    {
        if (!cx_is_admin($actor)) {
            throw new \RuntimeException('Yalnizca admin/superadmin.');
        }
        $n = $this->syncPublishedToActiveSystem();
        cx_audit_log((int) $actor['id'], 'listing.sync_published', 'trade_listings', 0, ['rows' => $n]);

        return $n;
    }

    /** @return array<string,int> */
    public function statusBreakdown(): array
    {
        $rows = $this->pdo->query(
            "SELECT UPPER(COALESCE(status,'')) AS st, COUNT(*) AS c
             FROM trade_listings GROUP BY UPPER(COALESCE(status,''))"
        )->fetchAll();
        $out = [];
        foreach ($rows as $r) {
            $out[(string) $r['st']] = (int) $r['c'];
        }

        return $out;
    }

    public static function lastListError(): ?string
    {
        return self::$lastListError;
    }

    /** @return array{raw:int,joined:int,error:?string,sample:?string} */
    public function listProbe(): array
    {
        $out = ['raw' => 0, 'joined' => 0, 'error' => null, 'sample' => null];
        try {
            $out['raw'] = (int) $this->pdo->query(
                "SELECT COUNT(*) FROM trade_listings WHERE UPPER(COALESCE(status,'')) <> 'CANCELLED'"
            )->fetchColumn();
            $stmt = $this->pdo->query(
                "SELECT l.id, l.title, l.status, u.username AS owner_username
                 FROM trade_listings l
                 LEFT JOIN users u ON u.id = l.owner_id
                 WHERE UPPER(COALESCE(l.status,'')) <> 'CANCELLED'
                 ORDER BY l.id DESC LIMIT 3"
            );
            $sample = $stmt->fetchAll() ?: [];
            $out['joined'] = count($sample);
            if ($sample !== []) {
                $out['sample'] = (string) ($sample[0]['title'] ?? '') . ' #' . (int) ($sample[0]['id'] ?? 0);
            }
        } catch (\Throwable $e) {
            $out['error'] = $e->getMessage();
        }

        return $out;
    }

    /**
     * @return list<array<string,mixed>>
     */
    public function list(
        ?string $q = null,
        ?string $statusFilter = null,
        int $limit = 120
    ): array {
        $this->safeEnsureSchema();
        self::$lastListError = null;

        try {
            $hasExpiry = $this->columnExists('trade_listings', 'expires_at')
                && $this->columnExists('trade_listings', 'published_at');

            $sql = "SELECT l.*, u.username AS owner_username
                    FROM trade_listings l
                    LEFT JOIN users u ON u.id = l.owner_id
                    WHERE UPPER(COALESCE(l.status,'')) <> 'CANCELLED'";
            $args = [];

            if ($statusFilter === 'pending') {
                // Tum onay kuyrugu — suresi dolmus bekleyenler "Suresi dolan" sekmesinde ayrica filtrelenir
                $sql .= " AND UPPER(l.status) IN ('PENDING_MODERATION','PENDING')";
            } elseif ($statusFilter === 'expired') {
                if (!$hasExpiry) {
                    return [];
                }
                $sql .= " AND UPPER(l.status) IN ('PENDING_MODERATION','PENDING')
                          AND l.published_at IS NOT NULL AND l.expires_at IS NOT NULL AND l.expires_at <= ?";
                $args[] = microtime(true);
            } elseif ($statusFilter === 'approved') {
                $sql .= " AND UPPER(l.status) IN ('APPROVED','ACTIVE')";
            } elseif ($statusFilter === 'rejected') {
                $sql .= " AND UPPER(l.status) = 'REJECTED'";
            } elseif ($statusFilter === 'sold') {
                $sql .= " AND UPPER(l.status) = 'SOLD'";
            }

            if ($q !== null && $q !== '') {
                $lid = cx_parse_listing_no($q, $this->listingNoBase);
                if ($lid !== null) {
                    $sql .= ' AND l.id = ?';
                    $args[] = $lid;
                } else {
                    $sql .= ' AND (l.title LIKE ? OR l.description LIKE ? OR l.subcategory LIKE ? OR COALESCE(u.username, \'\') LIKE ? OR CAST(l.id AS CHAR) LIKE ?)';
                    $like = '%' . $q . '%';
                    $args[] = $like;
                    $args[] = $like;
                    $args[] = $like;
                    $args[] = $like;
                    $args[] = $like;
                }
            }

            $sql .= ' ORDER BY ' . $this->listOrderBy() . ' LIMIT ' . (int) $limit;
            $stmt = $this->pdo->prepare($sql);
            $stmt->execute($args);
            $rows = $stmt->fetchAll() ?: [];

            $out = [];
            foreach ($rows as $row) {
                try {
                    $out[] = $this->enrichListRow($row);
                } catch (\Throwable $rowErr) {
                    @error_log('[BenimBazar] enrichListRow id=' . (int) ($row['id'] ?? 0) . ' ' . $rowErr->getMessage());
                    $out[] = $this->enrichListRowMinimal($row);
                }
            }

            return $out;
        } catch (\Throwable $e) {
            self::$lastListError = $e->getMessage();
            @error_log('[BenimBazar] AdminListingService::list ' . $e->getMessage());

            return [];
        }
    }

    /** @return list<array<string,mixed>> */
    public function topViewed(int $limit = 30): array
    {
        try {
            $limit = max(1, min(100, $limit));
            $this->safeEnsureSchema();
            $hasViewCount = $this->columnExists('trade_listings', 'view_count');
            $orderBy = $hasViewCount
                ? 'COALESCE(l.view_count, 0) DESC, l.id DESC'
                : 'l.updated_at DESC, l.id DESC';
            $stmt = $this->pdo->query(
                "SELECT l.*, u.username AS owner_username
                 FROM trade_listings l
                 LEFT JOIN users u ON u.id = l.owner_id
                 WHERE UPPER(COALESCE(l.status,'')) <> 'CANCELLED'
                 ORDER BY {$orderBy}
                 LIMIT " . $limit
            );
            $rows = $stmt->fetchAll() ?: [];
            foreach ($rows as &$row) {
                $row = $this->enrichListRow($row);
            }
            unset($row);

            return $rows;
        } catch (\Throwable $e) {
            @error_log('[BenimBazar] AdminListingService::topViewed ' . $e->getMessage());

            return [];
        }
    }

    private function safeEnsureSchema(): void
    {
        try {
            ListingSchemaService::ensure();
        } catch (\Throwable) {
        }
        try {
            SocialService::ensureTables();
        } catch (\Throwable) {
        }
    }

    /** @param array<string,mixed> $row */
    private function enrichListRow(array $row): array
    {
        $row['listing_no'] = $this->listingNoBase + (int) $row['id'];
        $row['photo_thumb'] = cx_photo_urls($row['photo_urls'] ?? '[]')[0] ?? null;
        $row['view_count'] = (int) ($row['view_count'] ?? 0);
        $row['owner_username'] = (string) ($row['owner_username'] ?? '—');
        try {
            $row['favorite_count'] = SocialService::favoriteCount((int) $row['id']);
        } catch (\Throwable) {
            $row['favorite_count'] = 0;
        }
        $row['message_count'] = cx_listing_message_count((int) $row['id']);
        $row['days_live'] = function_exists('cx_listing_days_live')
            ? cx_listing_days_live($row)
            : 0;

        return $row;
    }

    private function listOrderBy(): string
    {
        $hasUpdated = $this->columnExists('trade_listings', 'updated_at');
        $hasCreated = $this->columnExists('trade_listings', 'created_at');
        if ($hasUpdated && $hasCreated) {
            return 'COALESCE(l.updated_at, l.created_at, 0) DESC, l.id DESC';
        }
        if ($hasUpdated) {
            return 'l.updated_at DESC, l.id DESC';
        }
        if ($hasCreated) {
            return 'l.created_at DESC, l.id DESC';
        }

        return 'l.id DESC';
    }

    /** @param array<string,mixed> $row */
    private function enrichListRowMinimal(array $row): array
    {
        $row['listing_no'] = $this->listingNoBase + (int) ($row['id'] ?? 0);
        $row['photo_thumb'] = null;
        $row['view_count'] = (int) ($row['view_count'] ?? 0);
        $row['owner_username'] = (string) ($row['owner_username'] ?? '—');
        $row['favorite_count'] = 0;
        $row['message_count'] = 0;
        $row['days_live'] = 0;

        return $row;
    }

    private function columnExists(string $table, string $column): bool
    {
        try {
            $stmt = $this->pdo->prepare(
                'SHOW COLUMNS FROM `' . str_replace('`', '', $table) . '` LIKE ?'
            );
            $stmt->execute([$column]);

            return (bool) $stmt->fetch();
        } catch (\Throwable) {
            return false;
        }
    }

    /** @return array<string,mixed>|null */
    /**
     * Belirli kullanicinin ilanlari (yonetim).
     *
     * @return list<array<string,mixed>>
     */
    public function listByOwner(int $ownerId, ?string $statusFilter = null, int $limit = 200): array
    {
        if ($ownerId <= 0) {
            return [];
        }
        $this->safeEnsureSchema();
        $sql = "SELECT l.*, u.username AS owner_username
                FROM trade_listings l
                LEFT JOIN users u ON u.id = l.owner_id
                WHERE l.owner_id = ?";
        $args = [$ownerId];

        if ($statusFilter === 'pending') {
            $sql .= " AND UPPER(l.status) IN ('PENDING_MODERATION','PENDING')";
        } elseif ($statusFilter === 'approved') {
            $sql .= " AND UPPER(l.status) IN ('APPROVED','ACTIVE')";
        } elseif ($statusFilter === 'rejected') {
            $sql .= " AND UPPER(l.status) = 'REJECTED'";
        } elseif ($statusFilter === 'sold') {
            $sql .= " AND UPPER(l.status) = 'SOLD'";
        } elseif ($statusFilter === 'cancelled') {
            $sql .= " AND UPPER(l.status) = 'CANCELLED'";
        } else {
            // varsayilan: silinmemis tumu
            $sql .= " AND UPPER(COALESCE(l.status,'')) <> 'CANCELLED'";
        }

        $sql .= ' ORDER BY l.created_at DESC LIMIT ' . max(1, min(300, $limit));
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($args);
        $rows = $stmt->fetchAll() ?: [];
        $out = [];
        foreach ($rows as $row) {
            try {
                $out[] = $this->enrichListRow($row);
            } catch (\Throwable) {
                $out[] = $this->enrichListRowMinimal($row);
            }
        }

        return $out;
    }

    public function find(int $id): ?array
    {
        $stmt = $this->pdo->prepare(
            "SELECT l.*, u.username AS owner_username, u.email AS owner_email
             FROM trade_listings l
             LEFT JOIN users u ON u.id = l.owner_id
             WHERE l.id = ? LIMIT 1"
        );
        $stmt->execute([$id]);
        $row = $stmt->fetch();
        if (!$row) {
            return null;
        }
        $row['listing_no'] = $this->listingNoBase + (int) $row['id'];
        $row['photos'] = cx_photo_urls($row['photo_urls'] ?? '[]');
        return $row;
    }

    public function setStatus(int $id, string $status, array $actor, string $reason = ''): void
    {
        $status = strtoupper(trim($status));
        $reason = mb_substr(trim($reason), 0, 500);
        $row = $this->find($id);
        if ($row === null) {
            throw new \RuntimeException('Ilan bulunamadi.');
        }
        $old = strtoupper((string) ($row['status'] ?? ''));
        cx_assert_staff_may_set_status($actor, $status);
        if ($old === $status) {
            return;
        }
        if ($status === 'REJECTED' && $reason === '') {
            throw new \RuntimeException('Ret için kısa bir neden yazın; kullanıcıya bildirim olarak gönderilir.');
        }

        $hasModerationReason = false;
        try {
            $hasModerationReason = (bool) $this->pdo->query(
                'SHOW COLUMNS FROM trade_listings LIKE ' . $this->pdo->quote('moderation_reason')
            )->fetch();
        } catch (\Throwable) {
            $hasModerationReason = false;
        }

        if ($status === 'REJECTED' && $hasModerationReason) {
            $this->pdo->prepare(
                'UPDATE trade_listings SET status = ?, moderation_reason = ?, updated_at = ? WHERE id = ?'
            )->execute([$status, $reason, microtime(true), $id]);
        } else {
            $this->pdo->prepare('UPDATE trade_listings SET status = ?, updated_at = ? WHERE id = ?')
                ->execute([$status, microtime(true), $id]);
        }

        if (in_array($status, ['APPROVED', 'ACTIVE'], true)) {
            (new ListingLifecycleService())->renewAfterApproval($id);
            require_once __DIR__ . '/PriceDropAlertService.php';
            (new PriceDropAlertService())->flushPendingForListing($id);
            $ownerId = (int) ($row['owner_id'] ?? 0);
            if ($ownerId > 0) {
                $listingTitle = (string) ($row['title'] ?? '');
                $body = "İlanınız onaylanmıştır.\n\n"
                    . "«{$listingTitle}» artık yayında.\n\n"
                    . 'Kontrol edebilirsiniz.';
                NotificationService::create(
                    $ownerId,
                    'admin_approved',
                    'İlanınız onaylanmıştır',
                    $body,
                    'trade_listing',
                    $id,
                    true
                );
            }
        } elseif ($status === 'REJECTED') {
            $ownerId = (int) ($row['owner_id'] ?? 0);
            if ($ownerId > 0) {
                $title = (string) ($row['title'] ?? '');
                $body = "İlanınız «{$title}» reddedildi.\n\n"
                    . "Ret nedeni:\n{$reason}\n\n"
                    . 'Lütfen ilanı düzenleyip tekrar gönderin.';
                NotificationService::create(
                    $ownerId,
                    'admin_rejected',
                    'İlan reddedildi',
                    $body,
                    'trade_listing',
                    $id,
                    true
                );
            }
        } elseif (in_array($status, ['CANCELLED', 'SOLD'], true) && cx_listing_is_public($old)) {
            require_once __DIR__ . '/PriceDropAlertService.php';
            (new PriceDropAlertService())->notifyListingGone(
                $id,
                $status === 'SOLD' ? 'sold' : 'removed',
                (string) ($row['title'] ?? ''),
                (int) ($row['owner_id'] ?? 0)
            );
        }

        cx_audit_log((int) $actor['id'], 'listing.set_status', 'trade_listing', $id, [
            'from' => $old,
            'to' => $status,
            'reason' => $status === 'REJECTED' ? $reason : null,
        ]);
    }

    /**
     * @param array<string,mixed> $data
     * @param array<string,mixed> $actor
     */
    public function update(int $id, array $data, array $actor): void
    {
        $oldRow = $this->find($id);
        if ($oldRow === null) {
            throw new \RuntimeException('Ilan bulunamadi.');
        }

        $subcatSlug = trim((string) ($data['listing_subcat'] ?? ''));
        $resolved = cx_resolve_listing_category($subcatSlug);
        if ($resolved === null) {
            throw new \RuntimeException('Gecersiz kategori.');
        }

        $photosRaw = trim((string) ($data['photo_urls_text'] ?? ''));
        $existingPhotoRow = $this->pdo->prepare('SELECT photo_urls FROM trade_listings WHERE id = ? LIMIT 1');
        $existingPhotoRow->execute([$id]);
        $existingPhotosRaw = cx_listing_photo_stubs($existingPhotoRow->fetchColumn());

        if ($photosRaw !== '') {
            $photos = [];
            foreach (preg_split('/[\r\n,]+/', $photosRaw) ?: [] as $line) {
                $u = trim($line);
                if ($u !== '') {
                    $photos[] = $u;
                }
            }
        } elseif (isset($data['photo_editor'])) {
            $photos = cx_listing_photos_from_keep($data, $existingPhotosRaw);
            $photos = cx_listing_photos_apply_cover($photos, trim((string) ($data['cover_photo'] ?? '')) ?: null);
        } else {
            $photos = $existingPhotosRaw;
        }

        $attrsRaw = trim((string) ($data['attrs_json_text'] ?? ''));
        $attrsJson = null;

        $existingAttrs = null;
        $hasAttrsCol = (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();
        if ($hasAttrsCol) {
            $ex = $this->pdo->prepare('SELECT attrs_json FROM trade_listings WHERE id = ? LIMIT 1');
            $ex->execute([$id]);
            $rawExisting = $ex->fetchColumn();
            if (is_string($rawExisting) && $rawExisting !== '') {
                $decodedExisting = json_decode($rawExisting, true);
                if (is_array($decodedExisting)) {
                    $existingAttrs = $decodedExisting;
                }
            }
        }

        $vehSegment = trim((string) ($resolved['veh'] ?? ''));
        if ($vehSegment !== '' && isset(cx_vehicle_segments()[$vehSegment])) {
            $post = $data;
            $post['vehicle_segment'] = $vehSegment;
            $vehiclePack = cx_vehicle_attrs_merge_admin($post, $existingAttrs);
            if ($vehiclePack['error'] !== null) {
                throw new \RuntimeException($vehiclePack['error']);
            }
            if ($vehiclePack['attrs'] !== null) {
                $attrsJson = json_encode($vehiclePack['attrs'], JSON_UNESCAPED_UNICODE);
            }
        }

        if ($attrsJson === null && $attrsRaw !== '') {
            $decoded = json_decode($attrsRaw, true);
            if (!is_array($decoded)) {
                throw new \RuntimeException('attrs_json gecersiz JSON.');
            }
            if (!isset($decoded['segment']) && $vehSegment !== '') {
                $decoded['segment'] = $vehSegment;
            }
            $attrsJson = json_encode($decoded, JSON_UNESCAPED_UNICODE);
        }

        $mode = strtoupper(trim((string) ($data['listing_mode'] ?? 'TRADE')));
        $descErr = cx_listing_description_error((string) ($data['description'] ?? ''));
        if ($descErr !== null) {
            throw new \RuntimeException($descErr);
        }
        $price = $mode === 'SALE' ? (float) ($data['price_tl'] ?? 0) : null;
        if ($mode === 'SALE' && ($price === null || $price <= 0)) {
            throw new \RuntimeException('Satilik ilan icin fiyat girin.');
        }

        $newStatus = strtoupper(trim((string) ($data['status'] ?? 'PENDING_MODERATION')));
        cx_assert_staff_may_set_status($actor, $newStatus);

        $hasAttrs = (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'attrs_json'")->fetch();

        $fields = [
            'title' => trim((string) ($data['title'] ?? '')),
            'description' => trim((string) ($data['description'] ?? '')),
            'category' => $resolved['category'],
            'subcategory' => $resolved['subcategory'],
            'location' => trim((string) ($data['location'] ?? '')),
            'wanted_items' => trim((string) ($data['wanted_items'] ?? '')),
            'listing_mode' => $mode,
            'price_tl' => $price,
            'price_negotiable' => !empty($data['price_negotiable']) ? 1 : 0,
            'status' => $newStatus,
            'photo_urls' => json_encode($photos, JSON_UNESCAPED_UNICODE) ?: '[]',
            'updated_at' => microtime(true),
        ];

        if ($fields['title'] === '' || $fields['description'] === '') {
            throw new \RuntimeException('Baslik ve aciklama zorunlu.');
        }

        if ($hasAttrs) {
            if ($attrsJson !== null) {
                $this->pdo->prepare(
                    'UPDATE trade_listings SET
                      title = ?, description = ?, category = ?, subcategory = ?, location = ?,
                      wanted_items = ?, listing_mode = ?, price_tl = ?, price_negotiable = ?,
                      status = ?, photo_urls = ?, attrs_json = ?, updated_at = ?
                     WHERE id = ?'
                )->execute([
                    $fields['title'],
                    $fields['description'],
                    $fields['category'],
                    $fields['subcategory'],
                    $fields['location'],
                    $fields['wanted_items'],
                    $fields['listing_mode'],
                    $fields['price_tl'],
                    $fields['price_negotiable'],
                    $fields['status'],
                    $fields['photo_urls'],
                    $attrsJson,
                    $fields['updated_at'],
                    $id,
                ]);
            } else {
                $this->pdo->prepare(
                    'UPDATE trade_listings SET
                      title = ?, description = ?, category = ?, subcategory = ?, location = ?,
                      wanted_items = ?, listing_mode = ?, price_tl = ?, price_negotiable = ?,
                      status = ?, photo_urls = ?, updated_at = ?
                     WHERE id = ?'
                )->execute([
                    $fields['title'],
                    $fields['description'],
                    $fields['category'],
                    $fields['subcategory'],
                    $fields['location'],
                    $fields['wanted_items'],
                    $fields['listing_mode'],
                    $fields['price_tl'],
                    $fields['price_negotiable'],
                    $fields['status'],
                    $fields['photo_urls'],
                    $fields['updated_at'],
                    $id,
                ]);
            }
        } else {
            $this->pdo->prepare(
                'UPDATE trade_listings SET
                  title = ?, description = ?, category = ?, subcategory = ?, location = ?,
                  wanted_items = ?, listing_mode = ?, price_tl = ?, price_negotiable = ?,
                  status = ?, photo_urls = ?, updated_at = ?
                 WHERE id = ?'
            )->execute([
                $fields['title'],
                $fields['description'],
                $fields['category'],
                $fields['subcategory'],
                $fields['location'],
                $fields['wanted_items'],
                $fields['listing_mode'],
                $fields['price_tl'],
                $fields['price_negotiable'],
                $fields['status'],
                $fields['photo_urls'],
                $fields['updated_at'],
                $id,
            ]);
        }

        cx_audit_log((int) $actor['id'], 'listing.admin_update', 'trade_listing', $id, [
            'status' => $fields['status'],
        ]);

        $newStmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $newStmt->execute([$id]);
        $newRow = $newStmt->fetch(\PDO::FETCH_ASSOC);
        if (is_array($newRow)) {
            require_once __DIR__ . '/PriceDropAlertService.php';
            $defer = !in_array(strtoupper((string) ($newRow['status'] ?? '')), ['APPROVED', 'ACTIVE'], true);
            (new PriceDropAlertService())->handleListingPriceChange($id, $oldRow, $newRow, $defer);
        }

        if (in_array($fields['status'], ['APPROVED', 'ACTIVE'], true)) {
            (new ListingLifecycleService())->renewAfterApproval($id);
            require_once __DIR__ . '/PriceDropAlertService.php';
            (new PriceDropAlertService())->flushPendingForListing($id);
        }
    }

    public function requestEdit(int $id, array $actor, string $note = ''): void
    {
        $row = $this->find($id);
        if ($row === null) {
            throw new \RuntimeException('Ilan bulunamadi.');
        }
        $this->pdo->prepare(
            'UPDATE trade_listings SET status = ?, moderation_reason = ?, updated_at = ? WHERE id = ?'
        )->execute(['PENDING_MODERATION', trim($note), microtime(true), $id]);
        $ownerId = (int) ($row['owner_id'] ?? 0);
        if ($ownerId > 0) {
            NotificationService::create(
                $ownerId,
                'admin_edit_request',
                'Duzenleme istendi',
                trim($note) !== '' ? $note : 'Ilaninizda duzenleme yapmaniz istendi.',
                'trade_listing',
                $id,
                true
            );
        }
        cx_audit_log((int) $actor['id'], 'listing.request_edit', 'trade_listing', $id, ['note' => $note]);
    }
}
