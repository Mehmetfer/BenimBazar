<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;
use RuntimeException;

/** Satildi, yeniden yayin, 90 gun suresi, bakim cron. */
final class ListingLifecycleService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
    }

    /** Yayina al — published_at / expires_at ayarla. */
    public function markPublished(int $listingId): void
    {
        if (!$this->hasLifecycleColumns()) {
            return;
        }
        $now = microtime(true);
        $expires = $now + (cx_listing_ttl_days() * 86400);
        $this->pdo->prepare(
            'UPDATE trade_listings SET published_at = ?, expires_at = ?, updated_at = ? WHERE id = ?'
        )->execute([$now, $expires, $now, $listingId]);
    }

    /** Sahip: satildi isaretle. */
    public function markSold(int $listingId, int $ownerId): void
    {
        $stmt = $this->pdo->prepare('SELECT owner_id, status, title FROM trade_listings WHERE id = ? LIMIT 1');
        $stmt->execute([$listingId]);
        $row = $stmt->fetch();
        if (!$row || (int) $row['owner_id'] !== $ownerId) {
            throw new RuntimeException('Bu ilani isaretleyemezsiniz.');
        }
        $status = strtoupper((string) ($row['status'] ?? ''));
        if (!in_array($status, ['APPROVED', 'ACTIVE'], true)) {
            throw new RuntimeException('Yalnizca yayindaki ilan satildi yapilabilir.');
        }
        $now = microtime(true);
        $this->pdo->prepare(
            'UPDATE trade_listings SET status = ?, sold_at = ?, updated_at = ? WHERE id = ?'
        )->execute(['SOLD', $now, $now, $listingId]);
        require_once __DIR__ . '/PriceDropAlertService.php';
        (new PriceDropAlertService())->notifyListingGone(
            $listingId,
            'sold',
            (string) ($row['title'] ?? ''),
            $ownerId
        );
    }

    /** Sahip: suresi dolan ilani yeniden moderasyona gonder. */
    public function requestRepublish(int $listingId, int $ownerId): void
    {
        $stmt = $this->pdo->prepare(
            'SELECT owner_id, status, expires_at, published_at FROM trade_listings WHERE id = ? LIMIT 1'
        );
        $stmt->execute([$listingId]);
        $row = $stmt->fetch();
        if (!$row || (int) $row['owner_id'] !== $ownerId) {
            throw new RuntimeException('Bu ilani yeniden yayinlayamazsiniz.');
        }
        $status = strtoupper((string) ($row['status'] ?? ''));
        $expired = self::isExpiredRow($row);
        if (!$expired && !in_array($status, ['REJECTED'], true)) {
            throw new RuntimeException('Bu ilan yeniden yayin icin uygun degil.');
        }
        $now = microtime(true);
        $this->pdo->prepare(
            'UPDATE trade_listings SET status = ?, updated_at = ? WHERE id = ?'
        )->execute(['PENDING_MODERATION', $now, $listingId]);

        NotificationService::create(
            $ownerId,
            'republish_requested',
            'Yeniden yayin talebi',
            'Ilaniniz moderasyon kuyruguna alindi.',
            'trade_listing',
            $listingId
        );
    }

    /** Admin onay sonrasi yenile. */
    public function renewAfterApproval(int $listingId): void
    {
        $this->markPublished($listingId);
    }

    /** Suresi dolanlari PENDING_MODERATION yap. */
    public function expireDueListings(): int
    {
        if (!$this->hasLifecycleColumns()) {
            return 0;
        }
        $now = microtime(true);
        $stmt = $this->pdo->prepare(
            "SELECT id, owner_id, title FROM trade_listings
             WHERE UPPER(COALESCE(status,'')) IN ('APPROVED','ACTIVE')
               AND expires_at IS NOT NULL AND expires_at <= ?"
        );
        $stmt->execute([$now]);
        $rows = $stmt->fetchAll();
        if ($rows === []) {
            return 0;
        }

        $upd = $this->pdo->prepare(
            "UPDATE trade_listings SET status = 'PENDING_MODERATION', updated_at = ? WHERE id = ?"
        );
        $count = 0;
        foreach ($rows as $row) {
            $upd->execute([$now, (int) $row['id']]);
            $ownerId = (int) ($row['owner_id'] ?? 0);
            if ($ownerId > 0) {
                NotificationService::create(
                    $ownerId,
                    'expiry_expired',
                    'Ilan suresi doldu',
                    'Ilaniniz "' . (string) ($row['title'] ?? '') . '" icin yayin suresi doldu. Yeniden yayinlayarak devam edebilirsiniz.',
                    'trade_listing',
                    (int) $row['id'],
                    true
                );
            }
            $count++;
        }

        return $count;
    }

    /** 7 / 3 / 1 gun kala bildirim. */
    public function sendExpiryReminders(): int
    {
        if (!$this->hasLifecycleColumns()) {
            return 0;
        }
        $sent = 0;
        foreach ([7 => 'expiry_soon_7', 3 => 'expiry_soon_3', 1 => 'expiry_soon_1'] as $days => $type) {
            $sent += $this->remindDaysBefore($days, $type);
        }

        return $sent;
    }

    /** Throttled bakim — bootstrap veya cron. */
    public static function runMaintenance(): void
    {
        $lock = dirname(__DIR__, 2) . '/storage/listing-maintenance.lock';
        $interval = 900;
        if (is_file($lock) && (time() - (int) filemtime($lock)) < $interval) {
            return;
        }
        @touch($lock);
        try {
            $svc = new self();
            $svc->expireDueListings();
            $svc->sendExpiryReminders();
        } catch (\Throwable) {
            // sessiz
        }
    }

    /** @param array<string,mixed> $row */
    public static function isExpiredRow(array $row): bool
    {
        $status = strtoupper((string) ($row['status'] ?? ''));
        if (!in_array($status, ['PENDING_MODERATION', 'PENDING'], true)) {
            return false;
        }
        $exp = (float) ($row['expires_at'] ?? 0);
        $pub = (float) ($row['published_at'] ?? 0);

        return $pub > 0 && $exp > 0 && $exp <= microtime(true);
    }

    private function remindDaysBefore(int $days, string $type): int
    {
        $now = microtime(true);
        $daySec = 86400;
        $windowStart = $now + (($days - 1) * $daySec);
        $windowEnd = $now + ($days * $daySec);

        $stmt = $this->pdo->prepare(
            "SELECT id, owner_id, title FROM trade_listings
             WHERE UPPER(COALESCE(status,'')) IN ('APPROVED','ACTIVE')
               AND expires_at IS NOT NULL
               AND expires_at > ? AND expires_at <= ?"
        );
        $stmt->execute([$windowStart, $windowEnd]);
        $sent = 0;
        foreach ($stmt->fetchAll() as $row) {
            $listingId = (int) $row['id'];
            $ownerId = (int) ($row['owner_id'] ?? 0);
            if ($ownerId <= 0) {
                continue;
            }
            if (NotificationService::existsRecent($ownerId, $type, 'trade_listing', $listingId, 86400 * 2)) {
                continue;
            }
            $title = (string) ($row['title'] ?? 'Ilaniniz');
            NotificationService::create(
                $ownerId,
                $type,
                'Yayin suresi doluyor',
                'Ilaniniz "' . $title . '" icin yayin suresi ' . $days . ' gun sonra doluyor. Yeniden onaylayarak devam edebilirsiniz.',
                'trade_listing',
                $listingId,
                true
            );
            $sent++;
        }

        return $sent;
    }

    private function hasLifecycleColumns(): bool
    {
        try {
            return (bool) $this->pdo->query("SHOW COLUMNS FROM trade_listings LIKE 'expires_at'")->fetch();
        } catch (\Throwable) {
            return false;
        }
    }
}
