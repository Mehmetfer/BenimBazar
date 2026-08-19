<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

require_once __DIR__ . '/NotificationService.php';
require_once __DIR__ . '/../Helpers/price-drop.php';

/** Favori ilanlarda akıllı bildirimler (fiyat, fotoğraf, kaldırma, satıcı cevabı). */
final class PriceDropAlertService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
        ListingSchemaService::ensurePriceDropAlerts();
    }

    public static function ensureSchema(): void
    {
        ListingSchemaService::ensurePriceDropAlerts();
    }

    /** @param array<string,mixed> $listing */
    public function attachFavoriteSnapshot(int $userId, int $listingId, array $listing): void
    {
        if ($userId <= 0 || $listingId <= 0) {
            return;
        }

        $price = cx_listing_effective_price($listing);
        if ($price === null) {
            $this->pdo->prepare(
                'UPDATE listing_favorites SET alert_enabled = 0, price_currency = NULL, price_amount = NULL WHERE user_id = ? AND listing_id = ?'
            )->execute([$userId, $listingId]);

            return;
        }

        $this->pdo->prepare(
            'UPDATE listing_favorites
             SET alert_enabled = 1, price_currency = ?, price_amount = ?
             WHERE user_id = ? AND listing_id = ?'
        )->execute([$price['currency'], $price['amount'], $userId, $listingId]);
    }

    public function toggleAlert(int $userId, int $listingId): bool
    {
        if (!SocialService::isFavorited($userId, $listingId)) {
            throw new \RuntimeException('Once ilani favorilere ekleyin.');
        }

        $stmt = $this->pdo->prepare(
            'SELECT alert_enabled FROM listing_favorites WHERE user_id = ? AND listing_id = ? LIMIT 1'
        );
        $stmt->execute([$userId, $listingId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        $enabled = !empty($row['alert_enabled']);
        $newVal = $enabled ? 0 : 1;
        $this->pdo->prepare(
            'UPDATE listing_favorites SET alert_enabled = ? WHERE user_id = ? AND listing_id = ?'
        )->execute([$newVal, $userId, $listingId]);

        return (bool) $newVal;
    }

    public function isAlertEnabled(int $userId, int $listingId): bool
    {
        if ($userId <= 0 || !SocialService::isFavorited($userId, $listingId)) {
            return false;
        }

        $stmt = $this->pdo->prepare(
            'SELECT alert_enabled FROM listing_favorites WHERE user_id = ? AND listing_id = ? LIMIT 1'
        );
        $stmt->execute([$userId, $listingId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        return $row !== false && !empty($row['alert_enabled']);
    }

    /**
     * @param array<string,mixed> $oldRow
     * @param array<string,mixed> $newRow
     */
    public function handleListingPriceChange(int $listingId, array $oldRow, array $newRow, bool $deferUntilPublic): void
    {
        try {
            (new PriceHistoryService())->recordFromRows($listingId, $oldRow, $newRow);
        } catch (\Throwable) {
            // fiyat gecmisi opsiyonel
        }

        if (!cx_price_drop_alerts_enabled()) {
            return;
        }

        $this->handlePriceWatch($listingId, $oldRow, $newRow, $deferUntilPublic);
        $this->handlePhotoWatch($listingId, $oldRow, $newRow, $deferUntilPublic);
    }

    public function notifyListingGone(int $listingId, string $kind, string $title, int $ownerId): void
    {
        if (!cx_price_drop_alerts_enabled() || $listingId <= 0) {
            return;
        }

        $kind = $kind === 'sold' ? 'sold' : 'removed';
        $type = $kind === 'sold' ? 'listing_sold' : 'listing_removed';
        $heading = $kind === 'sold' ? 'İlan satıldı' : 'İlan kaldırıldı';
        $line = $kind === 'sold'
            ? 'Favorilerinizdeki ilan satıldı olarak işaretlendi.'
            : 'Favorilerinizdeki ilan yayından kaldırıldı.';
        $title = trim($title) !== '' ? $title : 'İlan';

        $this->notifyWatchers($listingId, $ownerId, $type, $heading, $line . "\n\n«" . $title . '»', 86400 * 7, true);
        $this->clearPending($listingId);
    }

    public function notifySellerReply(int $recipientId, int $listingId, int $conversationId, string $preview, int $ownerId): bool
    {
        if (!cx_price_drop_alerts_enabled() || $recipientId <= 0 || $recipientId === $ownerId) {
            return false;
        }
        if ($listingId <= 0 || !SocialService::isFavorited($recipientId, $listingId)) {
            return false;
        }
        if (!$this->isAlertEnabled($recipientId, $listingId)) {
            return false;
        }
        if (NotificationService::existsRecent($recipientId, 'fav_seller_reply', 'conversation', $conversationId, 90)) {
            return true;
        }

        $body = 'Favorilediğiniz ilanın satıcısı cevap verdi.';
        $preview = trim($preview);
        if ($preview !== '') {
            $body .= "\n\n«" . $preview . '»';
        }

        NotificationService::create(
            $recipientId,
            'fav_seller_reply',
            'Satıcı cevap verdi',
            $body,
            'conversation',
            $conversationId,
            false
        );

        return true;
    }

    /**
     * @param array<string,mixed> $oldRow
     * @param array<string,mixed> $newRow
     */
    private function handlePriceWatch(int $listingId, array $oldRow, array $newRow, bool $deferUntilPublic): void
    {
        $oldPrice = cx_listing_effective_price($oldRow);
        $newPrice = cx_listing_effective_price($newRow);
        $public = !$deferUntilPublic && cx_listing_is_public((string) ($newRow['status'] ?? ''));
        $ownerId = (int) ($newRow['owner_id'] ?? 0);

        if ($newPrice === null) {
            $this->patchPendingPrice($listingId, null, null);

            return;
        }

        $rose = cx_listing_price_rose($oldPrice, $newPrice);
        $dropped = cx_listing_price_dropped($oldPrice, $newPrice);

        if (!$rose && !$dropped) {
            if ($public && $oldPrice !== null && $oldPrice['currency'] === $newPrice['currency']) {
                $this->syncSnapshotsUp($listingId, $newPrice);
            }
            $this->patchPendingPrice($listingId, null, null);

            return;
        }

        if (!$public) {
            $this->patchPendingPrice($listingId, $oldPrice, $newPrice);

            return;
        }

        if ($dropped && $oldPrice !== null) {
            $this->notifyPriceChange($listingId, $oldPrice, $newPrice, $ownerId, 'drop');
        } elseif ($rose && $oldPrice !== null) {
            $this->notifyPriceChange($listingId, $oldPrice, $newPrice, $ownerId, 'rise');
        }
        $this->patchPendingPrice($listingId, null, null);
    }

    /**
     * @param array<string,mixed> $oldRow
     * @param array<string,mixed> $newRow
     */
    private function handlePhotoWatch(int $listingId, array $oldRow, array $newRow, bool $deferUntilPublic): void
    {
        $oldCount = cx_listing_photo_count($oldRow);
        $newCount = cx_listing_photo_count($newRow);
        if ($newCount <= $oldCount) {
            $this->patchPendingPhotos($listingId, 0, 0);

            return;
        }

        $public = !$deferUntilPublic && cx_listing_is_public((string) ($newRow['status'] ?? ''));
        if (!$public) {
            $this->patchPendingPhotos($listingId, $oldCount, $newCount);

            return;
        }

        $title = trim((string) ($newRow['title'] ?? 'İlan'));
        $added = $newCount - $oldCount;
        $body = 'Favorilediğiniz ilana ' . $added . ' yeni fotoğraf eklendi.'
            . "\n\n«" . $title . '»'
            . "\n" . $oldCount . ' → ' . $newCount . ' fotoğraf.';
        $this->notifyWatchers(
            $listingId,
            (int) ($newRow['owner_id'] ?? 0),
            'fav_photos',
            'Yeni fotoğraf eklendi',
            $body,
            3600,
            false
        );
        $this->patchPendingPhotos($listingId, 0, 0);
    }

    public function flushPendingForListing(int $listingId): void
    {
        if (!cx_price_drop_alerts_enabled()) {
            return;
        }

        $pending = $this->loadPending($listingId);
        if ($pending === null) {
            return;
        }

        $stmt = $this->pdo->prepare('SELECT * FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$row || !cx_listing_is_public((string) ($row['status'] ?? ''))) {
            return;
        }

        $ownerId = (int) ($row['owner_id'] ?? 0);
        $current = cx_listing_effective_price($row);
        $oldCur = (string) ($pending['old_currency'] ?? '');
        if ($current !== null && $oldCur !== '') {
            $old = [
                'currency' => $oldCur,
                'amount' => (float) $pending['old_amount'],
            ];
            $new = [
                'currency' => (string) ($pending['new_currency'] ?? $current['currency']),
                'amount' => (float) ($pending['new_amount'] ?? $current['amount']),
            ];
            if ($current['currency'] === $new['currency']) {
                $new['amount'] = $current['amount'];
            }
            if (cx_listing_price_dropped($old, $new)) {
                $this->notifyPriceChange($listingId, $old, $new, $ownerId, 'drop');
            } elseif (cx_listing_price_rose($old, $new)) {
                $this->notifyPriceChange($listingId, $old, $new, $ownerId, 'rise');
            }
        }

        $oldPhotos = (int) ($pending['old_photo_count'] ?? 0);
        $newPhotos = (int) ($pending['new_photo_count'] ?? 0);
        $livePhotos = cx_listing_photo_count($row);
        if ($newPhotos > $oldPhotos) {
            $useNew = max($newPhotos, $livePhotos);
            $added = $useNew - $oldPhotos;
            if ($added > 0) {
                $title = trim((string) ($row['title'] ?? 'İlan'));
                $body = 'Favorilediğiniz ilana ' . $added . ' yeni fotoğraf eklendi.'
                    . "\n\n«" . $title . '»'
                    . "\n" . $oldPhotos . ' → ' . $useNew . ' fotoğraf.';
                $this->notifyWatchers($listingId, $ownerId, 'fav_photos', 'Yeni fotoğraf eklendi', $body, 3600, false);
            }
        }

        $this->clearPending($listingId);
    }

    /**
     * @param array{currency:string,amount:float} $oldPrice
     * @param array{currency:string,amount:float} $newPrice
     */
    private function notifyPriceChange(int $listingId, array $oldPrice, array $newPrice, int $ownerId, string $dir): void
    {
        $cfg = cx_price_drop_alert_settings();
        $dedup = $cfg['dedup_seconds'];
        $isDrop = $dir === 'drop';
        $type = $isDrop ? 'price_drop' : 'price_rise';
        $heading = $isDrop ? 'Fiyat düştü' : 'Fiyat yükseldi';

        $stmt = $this->pdo->prepare(
            'SELECT f.user_id, f.price_currency, f.price_amount, l.title
             FROM listing_favorites f
             JOIN trade_listings l ON l.id = f.listing_id
             WHERE f.listing_id = ? AND f.alert_enabled = 1'
        );
        $stmt->execute([$listingId]);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];

        $title = '';
        foreach ($rows as $row) {
            if ($title === '') {
                $title = trim((string) ($row['title'] ?? 'İlan'));
            }

            $userId = (int) ($row['user_id'] ?? 0);
            if ($userId <= 0 || $userId === $ownerId) {
                continue;
            }

            $baseline = null;
            $cur = strtoupper(trim((string) ($row['price_currency'] ?? '')));
            $amt = $row['price_amount'] ?? null;
            if ($cur !== '' && $amt !== null && $amt !== '') {
                $baseline = ['currency' => $cur, 'amount' => (float) $amt];
            }

            $compareOld = $baseline ?? $oldPrice;
            $changed = $isDrop
                ? cx_listing_price_dropped($compareOld, $newPrice)
                : cx_listing_price_rose($compareOld, $newPrice);
            if (!$changed) {
                continue;
            }

            if (NotificationService::existsRecent($userId, $type, 'trade_listing', $listingId, $dedup)) {
                $this->updateFavoriteSnapshot($userId, $listingId, $newPrice);
                continue;
            }

            $verb = $isDrop ? 'düştü' : 'yükseldi';
            $body = 'Takip ettiğiniz ilanın fiyatı ' . $verb . ':'
                . "\n\n«" . $title . '»'
                . "\n" . cx_listing_price_format($compareOld) . ' → ' . cx_listing_price_format($newPrice);

            NotificationService::create(
                $userId,
                $type,
                $heading,
                $body,
                'trade_listing',
                $listingId,
                $cfg['email']
            );

            $this->updateFavoriteSnapshot($userId, $listingId, $newPrice);
        }
    }

    private function notifyWatchers(
        int $listingId,
        int $ownerId,
        string $type,
        string $heading,
        string $body,
        int $dedupSeconds,
        bool $email
    ): void {
        $stmt = $this->pdo->prepare(
            'SELECT user_id FROM listing_favorites WHERE listing_id = ? AND alert_enabled = 1'
        );
        $stmt->execute([$listingId]);
        foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) ?: [] as $row) {
            $userId = (int) ($row['user_id'] ?? 0);
            if ($userId <= 0 || $userId === $ownerId) {
                continue;
            }
            if (NotificationService::existsRecent($userId, $type, 'trade_listing', $listingId, $dedupSeconds)) {
                continue;
            }
            NotificationService::create($userId, $type, $heading, $body, 'trade_listing', $listingId, $email);
        }
    }

    /** @param array{currency:string,amount:float} $price */
    private function updateFavoriteSnapshot(int $userId, int $listingId, array $price): void
    {
        $this->pdo->prepare(
            'UPDATE listing_favorites SET price_currency = ?, price_amount = ? WHERE user_id = ? AND listing_id = ?'
        )->execute([$price['currency'], $price['amount'], $userId, $listingId]);
    }

    /** @param array{currency:string,amount:float} $price */
    private function syncSnapshotsUp(int $listingId, array $price): void
    {
        $this->pdo->prepare(
            'UPDATE listing_favorites SET price_currency = ?, price_amount = ? WHERE listing_id = ? AND alert_enabled = 1'
        )->execute([$price['currency'], $price['amount'], $listingId]);
    }

    /** @param array{currency:string,amount:float}|null $old @param array{currency:string,amount:float}|null $new */
    private function patchPendingPrice(int $listingId, ?array $old, ?array $new): void
    {
        $pending = $this->loadPending($listingId) ?? [
            'old_currency' => '',
            'old_amount' => 0.0,
            'new_currency' => '',
            'new_amount' => 0.0,
            'old_photo_count' => 0,
            'new_photo_count' => 0,
        ];
        if ($old === null || $new === null) {
            $pending['old_currency'] = '';
            $pending['old_amount'] = 0.0;
            $pending['new_currency'] = '';
            $pending['new_amount'] = 0.0;
        } else {
            $pending['old_currency'] = $old['currency'];
            $pending['old_amount'] = $old['amount'];
            $pending['new_currency'] = $new['currency'];
            $pending['new_amount'] = $new['amount'];
        }
        $this->persistPending($listingId, $pending);
    }

    private function patchPendingPhotos(int $listingId, int $oldCount, int $newCount): void
    {
        $pending = $this->loadPending($listingId) ?? [
            'old_currency' => '',
            'old_amount' => 0.0,
            'new_currency' => '',
            'new_amount' => 0.0,
            'old_photo_count' => 0,
            'new_photo_count' => 0,
        ];
        $pending['old_photo_count'] = max(0, $oldCount);
        $pending['new_photo_count'] = max(0, $newCount);
        $this->persistPending($listingId, $pending);
    }

    /** @param array{old_currency:string,old_amount:float,new_currency:string,new_amount:float,old_photo_count:int,new_photo_count:int} $pending */
    private function persistPending(int $listingId, array $pending): void
    {
        $emptyPrice = ($pending['old_currency'] ?? '') === '' && (float) ($pending['old_amount'] ?? 0) === 0.0
            && ($pending['new_currency'] ?? '') === '';
        $emptyPhotos = (int) ($pending['old_photo_count'] ?? 0) === 0 && (int) ($pending['new_photo_count'] ?? 0) === 0;
        if ($emptyPrice && $emptyPhotos) {
            $this->clearPending($listingId);

            return;
        }

        try {
            $this->pdo->prepare(
                'REPLACE INTO listing_price_drop_pending
                 (listing_id, old_currency, old_amount, new_currency, new_amount, old_photo_count, new_photo_count, created_at)
                 VALUES (?,?,?,?,?,?,?,?)'
            )->execute([
                $listingId,
                (string) ($pending['old_currency'] ?? ''),
                (float) ($pending['old_amount'] ?? 0),
                (string) ($pending['new_currency'] ?? ''),
                (float) ($pending['new_amount'] ?? 0),
                (int) ($pending['old_photo_count'] ?? 0),
                (int) ($pending['new_photo_count'] ?? 0),
                microtime(true),
            ]);
        } catch (\Throwable) {
            $this->pdo->prepare(
                'REPLACE INTO listing_price_drop_pending
                 (listing_id, old_currency, old_amount, new_currency, new_amount, created_at)
                 VALUES (?,?,?,?,?,?)'
            )->execute([
                $listingId,
                (string) ($pending['old_currency'] ?? ''),
                (float) ($pending['old_amount'] ?? 0),
                (string) ($pending['new_currency'] ?? ''),
                (float) ($pending['new_amount'] ?? 0),
                microtime(true),
            ]);
        }
    }

    private function clearPending(int $listingId): void
    {
        $this->pdo->prepare('DELETE FROM listing_price_drop_pending WHERE listing_id = ?')->execute([$listingId]);
    }

    /**
     * @return array{
     *   old_currency:string,old_amount:float,new_currency:string,new_amount:float,
     *   old_photo_count:int,new_photo_count:int
     * }|null
     */
    private function loadPending(int $listingId): ?array
    {
        try {
            $stmt = $this->pdo->prepare(
                'SELECT old_currency, old_amount, new_currency, new_amount, old_photo_count, new_photo_count
                 FROM listing_price_drop_pending WHERE listing_id = ? LIMIT 1'
            );
            $stmt->execute([$listingId]);
        } catch (\Throwable) {
            $stmt = $this->pdo->prepare(
                'SELECT old_currency, old_amount, new_currency, new_amount
                 FROM listing_price_drop_pending WHERE listing_id = ? LIMIT 1'
            );
            $stmt->execute([$listingId]);
        }
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            return null;
        }

        return [
            'old_currency' => (string) ($row['old_currency'] ?? ''),
            'old_amount' => (float) ($row['old_amount'] ?? 0),
            'new_currency' => (string) ($row['new_currency'] ?? ''),
            'new_amount' => (float) ($row['new_amount'] ?? 0),
            'old_photo_count' => (int) ($row['old_photo_count'] ?? 0),
            'new_photo_count' => (int) ($row['new_photo_count'] ?? 0),
        ];
    }
}
