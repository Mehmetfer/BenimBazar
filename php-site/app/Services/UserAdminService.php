<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

require_once __DIR__ . '/ListingSchemaService.php';

final class UserAdminService
{
    /** @var list<string> */
    public const ASSIGNABLE = ['user', 'dealer', 'vip_kurumsal', 'moderator', 'admin'];

    /** @return array<string,string> */
    public static function roleLabels(): array
    {
        return [
            'user' => 'Uye',
            'dealer' => 'Kurumsal (Galeri)',
            'vip_kurumsal' => 'VIP Kurumsal',
            'moderator' => 'Onayci',
            'admin' => 'Yonetici',
            'superadmin' => 'Super Yonetici',
        ];
    }

    public static function label(string $role): string
    {
        return self::roleLabels()[$role] ?? $role;
    }

    /** @return list<array<string,mixed>> */
    public static function search(string $q = '', int $limit = 100): array
    {
        $pdo = Database::pdo();
        ListingSchemaService::ensureUserColumns();
        $cols = self::userSelectColumns($pdo);
        $sql = 'SELECT ' . implode(', ', $cols) . ' FROM users';
        $args = [];
        if ($q !== '') {
            $where = ['username LIKE ?', 'email LIKE ?'];
            $like = '%' . $q . '%';
            $args = [$like, $like];
            if (in_array('phone', $cols, true)) {
                $where[] = 'phone LIKE ?';
                $args[] = $like;
            }
            if (in_array('city', $cols, true)) {
                $where[] = 'city LIKE ?';
                $args[] = $like;
            }
            $sql .= ' WHERE ' . implode(' OR ', $where);
        }
        $sql .= ' ORDER BY id DESC LIMIT ' . max(1, min($limit, 200));
        $stmt = $pdo->prepare($sql);
        $stmt->execute($args);
        $rows = $stmt->fetchAll();
        foreach ($rows as &$row) {
            $row['country'] = cx_normalize_country((string) ($row['country'] ?? 'tr'));
        }
        unset($row);

        return self::attachListingCounts($rows);
    }

    /** @return list<string> */
    private static function userSelectColumns(PDO $pdo): array
    {
        $cols = ['id', 'username', 'role', 'email', 'change_score', 'suspended', 'created_at'];
        foreach (['country', 'phone', 'city', 'vip_starts_at', 'vip_ends_at'] as $optional) {
            if (self::columnExists($pdo, $optional)) {
                $cols[] = $optional;
            }
        }

        return $cols;
    }

    private static function columnExists(PDO $pdo, string $column): bool
    {
        try {
            return (bool) $pdo->query('SHOW COLUMNS FROM users LIKE ' . $pdo->quote($column))->fetch();
        } catch (\Throwable) {
            return false;
        }
    }

    /** YYYY-MM-DD veya null. */
    public static function normalizeVipDate(?string $raw): ?string
    {
        $raw = trim((string) $raw);
        if ($raw === '') {
            return null;
        }
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $raw)) {
            throw new \RuntimeException('VIP tarih formatı geçersiz (YYYY-MM-DD).');
        }
        $parts = array_map('intval', explode('-', $raw));
        if (!checkdate($parts[1], $parts[2], $parts[0])) {
            throw new \RuntimeException('VIP tarihi geçersiz.');
        }

        return $raw;
    }

    /**
     * @param list<array<string,mixed>> $rows
     * @return list<array<string,mixed>>
     */
    private static function attachListingCounts(array $rows): array
    {
        if ($rows === []) {
            return $rows;
        }
        $ids = [];
        foreach ($rows as $row) {
            $ids[] = (int) ($row['id'] ?? 0);
        }
        $ids = array_values(array_filter($ids, static fn (int $id): bool => $id > 0));
        if ($ids === []) {
            return $rows;
        }

        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $counts = [];
        foreach ($ids as $id) {
            $counts[$id] = [
                'listing_total' => 0,
                'listing_published' => 0,
                'listing_pending' => 0,
                'listing_sold' => 0,
                'listing_other' => 0,
            ];
        }

        try {
            $stmt = Database::pdo()->prepare(
                "SELECT owner_id,
                        COUNT(*) AS total,
                        SUM(CASE WHEN UPPER(COALESCE(status,'')) IN ('APPROVED','ACTIVE') THEN 1 ELSE 0 END) AS published,
                        SUM(CASE WHEN UPPER(COALESCE(status,'')) IN ('PENDING_MODERATION','PENDING') THEN 1 ELSE 0 END) AS pending,
                        SUM(CASE WHEN UPPER(COALESCE(status,'')) = 'SOLD' THEN 1 ELSE 0 END) AS sold
                 FROM trade_listings
                 WHERE owner_id IN ($placeholders)
                   AND UPPER(COALESCE(status,'')) <> 'CANCELLED'
                 GROUP BY owner_id"
            );
            $stmt->execute($ids);
            foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $c) {
                $oid = (int) ($c['owner_id'] ?? 0);
                if (!isset($counts[$oid])) {
                    continue;
                }
                $total = (int) ($c['total'] ?? 0);
                $published = (int) ($c['published'] ?? 0);
                $pending = (int) ($c['pending'] ?? 0);
                $sold = (int) ($c['sold'] ?? 0);
                $counts[$oid] = [
                    'listing_total' => $total,
                    'listing_published' => $published,
                    'listing_pending' => $pending,
                    'listing_sold' => $sold,
                    'listing_other' => max(0, $total - $published - $pending - $sold),
                ];
            }
        } catch (\Throwable) {
            // trade_listings yoksa sayilar 0 kalsin
        }

        foreach ($rows as &$row) {
            $oid = (int) ($row['id'] ?? 0);
            $row = array_merge($row, $counts[$oid] ?? [
                'listing_total' => 0,
                'listing_published' => 0,
                'listing_pending' => 0,
                'listing_sold' => 0,
                'listing_other' => 0,
            ]);
        }
        unset($row);

        return $rows;
    }

    /** @return array<string,mixed>|null */
    public static function findUser(int $userId): ?array
    {
        if ($userId <= 0) {
            return null;
        }
        $pdo = Database::pdo();
        ListingSchemaService::ensureUserColumns();
        $cols = self::userSelectColumns($pdo);
        $stmt = $pdo->prepare('SELECT ' . implode(', ', $cols) . ' FROM users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            return null;
        }
        $row['country'] = cx_normalize_country((string) ($row['country'] ?? 'tr'));
        $withCounts = self::attachListingCounts([$row]);

        return $withCounts[0] ?? $row;
    }

    /**
     * Superadmin: rol + (VIP ise) üyelik başlangıç/bitiş.
     */
    public static function assignRole(
        int $targetId,
        string $role,
        int $actorId,
        ?string $vipStartsAt = null,
        ?string $vipEndsAt = null
    ): void {
        $role = strtolower(trim($role));
        if ($role === 'superadmin') {
            throw new \RuntimeException('Baska kullaniciya superadmin atanamaz.');
        }
        if (!in_array($role, self::ASSIGNABLE, true)) {
            throw new \RuntimeException('Gecersiz rol: ' . $role);
        }

        $pdo = Database::pdo();
        ListingSchemaService::ensureUserColumns();
        $stmt = $pdo->prepare('SELECT id, username, role FROM users WHERE id = ? LIMIT 1');
        $stmt->execute([$targetId]);
        $target = $stmt->fetch();
        if (!$target) {
            throw new \RuntimeException('Kullanici bulunamadi.');
        }
        if (($target['role'] ?? '') === 'superadmin' && (int) $target['id'] !== $actorId) {
            throw new \RuntimeException('Superadmin rolu degistirilemez.');
        }
        if ((int) $target['id'] === $actorId && $role !== 'superadmin') {
            throw new \RuntimeException('Kendi superadmin rolunuzu dusuremezsiniz.');
        }

        $starts = null;
        $ends = null;
        if ($role === 'vip_kurumsal') {
            $starts = self::normalizeVipDate($vipStartsAt);
            $ends = self::normalizeVipDate($vipEndsAt);
            if ($starts !== null && $ends !== null && $ends < $starts) {
                throw new \RuntimeException('VIP bitiş tarihi, başlangıçtan önce olamaz.');
            }
            $pdo->prepare(
                'UPDATE users SET role = ?, vip_starts_at = ?, vip_ends_at = ? WHERE id = ?'
            )->execute([$role, $starts, $ends, $targetId]);
        } else {
            $pdo->prepare(
                'UPDATE users SET role = ?, vip_starts_at = NULL, vip_ends_at = NULL WHERE id = ?'
            )->execute([$role, $targetId]);
        }

        try {
            $pdo->prepare(
                'INSERT INTO audit_logs (actor_id, action, entity, entity_id, detail, created_at)
                 VALUES (?,?,?,?,?,?)'
            )->execute([
                $actorId,
                'admin.assign_role',
                'user',
                $targetId,
                json_encode([
                    'username' => $target['username'],
                    'from' => $target['role'],
                    'to' => $role,
                    'vip_starts_at' => $starts,
                    'vip_ends_at' => $ends,
                ], JSON_UNESCAPED_UNICODE),
                microtime(true),
            ]);
        } catch (\Throwable) {
            // audit_logs yoksa devam
        }
    }

    /**
     * Superadmin: yalnızca VIP üyelik tarihlerini güncelle (rol değişmez).
     */
    public static function updateVipMembershipDates(int $targetId, ?string $startsAt, ?string $endsAt, int $actorId): void
    {
        $pdo = Database::pdo();
        ListingSchemaService::ensureUserColumns();
        $stmt = $pdo->prepare('SELECT id, username, role, vip_starts_at, vip_ends_at FROM users WHERE id = ? LIMIT 1');
        $stmt->execute([$targetId]);
        $target = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$target) {
            throw new \RuntimeException('Kullanici bulunamadi.');
        }
        if ((string) ($target['role'] ?? '') !== 'vip_kurumsal') {
            throw new \RuntimeException('Üyelik tarihi yalnızca VIP Kurumsal hesaplar için ayarlanır.');
        }

        $starts = self::normalizeVipDate($startsAt);
        $ends = self::normalizeVipDate($endsAt);
        if ($starts !== null && $ends !== null && $ends < $starts) {
            throw new \RuntimeException('VIP bitiş tarihi, başlangıçtan önce olamaz.');
        }

        $pdo->prepare(
            'UPDATE users SET vip_starts_at = ?, vip_ends_at = ? WHERE id = ?'
        )->execute([$starts, $ends, $targetId]);

        try {
            $pdo->prepare(
                'INSERT INTO audit_logs (actor_id, action, entity, entity_id, detail, created_at)
                 VALUES (?,?,?,?,?,?)'
            )->execute([
                $actorId,
                'admin.vip_membership_dates',
                'user',
                $targetId,
                json_encode([
                    'username' => $target['username'],
                    'from' => [
                        'vip_starts_at' => $target['vip_starts_at'] ?? null,
                        'vip_ends_at' => $target['vip_ends_at'] ?? null,
                    ],
                    'to' => [
                        'vip_starts_at' => $starts,
                        'vip_ends_at' => $ends,
                    ],
                ], JSON_UNESCAPED_UNICODE),
                microtime(true),
            ]);
        } catch (\Throwable) {
            // audit_logs yoksa devam
        }
    }
}
