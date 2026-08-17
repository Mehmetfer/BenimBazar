<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

final class SocialService
{
    public static function ensureTables(): void
    {
        $pdo = Database::pdo();
        $pdo->exec(
            'CREATE TABLE IF NOT EXISTS listing_favorites (
              user_id INT UNSIGNED NOT NULL,
              listing_id INT UNSIGNED NOT NULL,
              created_at DOUBLE NOT NULL,
              PRIMARY KEY (user_id, listing_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
        );
    }

    public static function favoriteCount(int $listingId): int
    {
        $stmt = Database::pdo()->prepare(
            'SELECT COUNT(*) c FROM listing_favorites WHERE listing_id = ?'
        );
        $stmt->execute([$listingId]);
        $val = $stmt->fetchColumn();

        return is_numeric($val) ? (int) $val : 0;
    }

    public static function isFavorited(int $userId, int $listingId): bool
    {
        $stmt = Database::pdo()->prepare(
            'SELECT 1 FROM listing_favorites WHERE user_id = ? AND listing_id = ?'
        );
        $stmt->execute([$userId, $listingId]);
        return (bool) $stmt->fetch();
    }

    public static function toggleFavorite(int $userId, int $listingId): array
    {
        $pdo = Database::pdo();
        $st = $pdo->prepare('SELECT status FROM trade_listings WHERE id = ? LIMIT 1');
        $st->execute([$listingId]);
        $row = $st->fetch();
        if (!$row || !cx_listing_is_public((string) ($row['status'] ?? ''))) {
            throw new \RuntimeException('Bu ilan favorilere eklenemez.');
        }

        if (self::isFavorited($userId, $listingId)) {
            $pdo->prepare('DELETE FROM listing_favorites WHERE user_id = ? AND listing_id = ?')
                ->execute([$userId, $listingId]);
            $fav = false;
        } else {
            $pdo->prepare(
                'INSERT IGNORE INTO listing_favorites (user_id, listing_id, created_at) VALUES (?,?,?)'
            )->execute([$userId, $listingId, microtime(true)]);
            $fav = true;
        }
        return ['favorited' => $fav, 'favorite_count' => self::favoriteCount($listingId)];
    }

    /** @return list<array<string,mixed>> */
    public static function myFavorites(int $userId): array
    {
        $stmt = Database::pdo()->prepare(
            'SELECT l.*, u.username AS owner_username
             FROM listing_favorites f
             JOIN trade_listings l ON l.id = f.listing_id
             JOIN users u ON u.id = l.owner_id
             WHERE f.user_id = ?
             ORDER BY f.created_at DESC LIMIT 100'
        );
        $stmt->execute([$userId]);
        return $stmt->fetchAll();
    }

    public static function isFollowing(int $followerId, int $followingId): bool
    {
        if ($followerId === $followingId) {
            return false;
        }
        $stmt = Database::pdo()->prepare(
            'SELECT 1 FROM user_follows WHERE follower_id = ? AND following_id = ?'
        );
        $stmt->execute([$followerId, $followingId]);
        return (bool) $stmt->fetch();
    }

    public static function toggleFollow(int $followerId, int $followingId): bool
    {
        if ($followerId === $followingId) {
            return false;
        }
        $pdo = Database::pdo();
        if (self::isFollowing($followerId, $followingId)) {
            $pdo->prepare('DELETE FROM user_follows WHERE follower_id = ? AND following_id = ?')
                ->execute([$followerId, $followingId]);
            return false;
        }
        $pdo->prepare(
            'INSERT IGNORE INTO user_follows (follower_id, following_id, created_at) VALUES (?,?,?)'
        )->execute([$followerId, $followingId, microtime(true)]);
        return true;
    }

    /**
     * Feed icin toplu istatistik — N+1 sorgulari onler.
     *
     * @param list<int> $listingIds
     * @param list<int> $ownerIds
     * @return array{
     *   favorite_counts: array<int,int>,
     *   favorited_ids: array<int,bool>,
     *   following_ids: array<int,bool>
     * }
     */
    public static function bulkFeedStats(array $listingIds, ?int $viewerId, array $ownerIds = []): array
    {
        $listingIds = array_values(array_unique(array_filter(array_map('intval', $listingIds))));
        $ownerIds = array_values(array_unique(array_filter(array_map('intval', $ownerIds))));
        $out = [
            'favorite_counts' => [],
            'favorited_ids' => [],
            'following_ids' => [],
        ];
        if ($listingIds === []) {
            return $out;
        }

        $pdo = Database::pdo();
        $placeholders = implode(',', array_fill(0, count($listingIds), '?'));
        $stmt = $pdo->prepare(
            "SELECT listing_id, COUNT(*) AS c
             FROM listing_favorites
             WHERE listing_id IN ($placeholders)
             GROUP BY listing_id"
        );
        $stmt->execute($listingIds);
        foreach ($stmt->fetchAll() as $row) {
            $out['favorite_counts'][(int) $row['listing_id']] = (int) $row['c'];
        }

        if ($viewerId !== null && $viewerId > 0) {
            $stmt = $pdo->prepare(
                "SELECT listing_id FROM listing_favorites
                 WHERE user_id = ? AND listing_id IN ($placeholders)"
            );
            $stmt->execute(array_merge([$viewerId], $listingIds));
            foreach ($stmt->fetchAll() as $row) {
                $out['favorited_ids'][(int) $row['listing_id']] = true;
            }

            if ($ownerIds !== []) {
                $oPlace = implode(',', array_fill(0, count($ownerIds), '?'));
                $stmt = $pdo->prepare(
                    "SELECT following_id FROM user_follows
                     WHERE follower_id = ? AND following_id IN ($oPlace)"
                );
                $stmt->execute(array_merge([$viewerId], $ownerIds));
                foreach ($stmt->fetchAll() as $row) {
                    $out['following_ids'][(int) $row['following_id']] = true;
                }
            }
        }

        return $out;
    }
}
