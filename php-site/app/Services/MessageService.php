<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;
use RuntimeException;

/** Alıcı–satıcı mesajlaşma (ilan veya galeri bazlı). */
final class MessageService
{
    private const MAX_BODY_LEN = 2000;
    private const RATE_LIMIT_PER_MIN = 12;

    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
        self::ensureTables();
    }

    public static function ensureTables(): void
    {
        try {
            $pdo = Database::pdo();
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS message_conversations (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  listing_id INT UNSIGNED NULL,
                  created_at DOUBLE NOT NULL,
                  updated_at DOUBLE NOT NULL,
                  PRIMARY KEY (id),
                  KEY idx_conv_listing (listing_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS message_participants (
                  conversation_id INT UNSIGNED NOT NULL,
                  user_id INT UNSIGNED NOT NULL,
                  joined_at DOUBLE NOT NULL,
                  PRIMARY KEY (conversation_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS messages (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  conversation_id INT UNSIGNED NOT NULL,
                  sender_id INT UNSIGNED NOT NULL,
                  body TEXT NOT NULL,
                  created_at DOUBLE NOT NULL,
                  read_at DOUBLE NULL,
                  PRIMARY KEY (id),
                  KEY idx_msg_conv (conversation_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
        } catch (\Throwable) {
            // yetki / eski MySQL
        }
    }

    public function findOrCreateForListing(int $listingId, int $buyerId, int $sellerId): int
    {
        if ($listingId <= 0 || $buyerId <= 0 || $sellerId <= 0) {
            throw new RuntimeException('Geçersiz sohbet parametreleri.');
        }
        if ($buyerId === $sellerId) {
            throw new RuntimeException('Kendi ilanınıza mesaj gönderemezsiniz.');
        }

        $existing = $this->findConversationId($listingId, $buyerId, $sellerId);
        if ($existing > 0) {
            return $existing;
        }

        $now = microtime(true);
        $this->pdo->beginTransaction();
        try {
            $this->pdo->prepare(
                'INSERT INTO message_conversations (listing_id, created_at, updated_at) VALUES (?,?,?)'
            )->execute([$listingId, $now, $now]);
            $convId = (int) $this->pdo->lastInsertId();
            $ins = $this->pdo->prepare(
                'INSERT INTO message_participants (conversation_id, user_id, joined_at) VALUES (?,?,?)'
            );
            $ins->execute([$convId, $buyerId, $now]);
            $ins->execute([$convId, $sellerId, $now]);
            $this->pdo->commit();

            return $convId;
        } catch (\Throwable $e) {
            $this->pdo->rollBack();
            throw $e;
        }
    }

    public function findOrCreateForSeller(int $sellerId, int $buyerId): int
    {
        if ($sellerId <= 0 || $buyerId <= 0) {
            throw new RuntimeException('Geçersiz sohbet parametreleri.');
        }
        if ($buyerId === $sellerId) {
            throw new RuntimeException('Kendinize mesaj gönderemezsiniz.');
        }

        $existing = $this->findConversationId(null, $buyerId, $sellerId);
        if ($existing > 0) {
            return $existing;
        }

        $now = microtime(true);
        $this->pdo->beginTransaction();
        try {
            $this->pdo->prepare(
                'INSERT INTO message_conversations (listing_id, created_at, updated_at) VALUES (NULL,?,?)'
            )->execute([$now, $now]);
            $convId = (int) $this->pdo->lastInsertId();
            $ins = $this->pdo->prepare(
                'INSERT INTO message_participants (conversation_id, user_id, joined_at) VALUES (?,?,?)'
            );
            $ins->execute([$convId, $buyerId, $now]);
            $ins->execute([$convId, $sellerId, $now]);
            $this->pdo->commit();

            return $convId;
        } catch (\Throwable $e) {
            $this->pdo->rollBack();
            throw $e;
        }
    }

    /** @return list<array<string,mixed>> */
    public function inbox(int $userId, int $limit = 50): array
    {
        if ($userId <= 0) {
            return [];
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT c.id, c.listing_id, c.updated_at,
                        l.title AS listing_title,
                        (SELECT body FROM messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS last_body,
                        (SELECT COUNT(*) FROM messages m
                         WHERE m.conversation_id = c.id AND m.sender_id != ? AND m.read_at IS NULL) AS unread_count,
                        (SELECT u.username FROM message_participants mp
                         JOIN users u ON u.id = mp.user_id
                         WHERE mp.conversation_id = c.id AND mp.user_id != ? LIMIT 1) AS other_username
                 FROM message_conversations c
                 JOIN message_participants p ON p.conversation_id = c.id
                 LEFT JOIN trade_listings l ON l.id = c.listing_id
                 WHERE p.user_id = ?
                 ORDER BY c.updated_at DESC
                 LIMIT ' . (int) $limit
            );
            $stmt->execute([$userId, $userId, $userId]);

            return $stmt->fetchAll() ?: [];
        } catch (\Throwable) {
            return [];
        }
    }

    /** @return array<string,mixed>|null */
    public function conversationForUser(int $conversationId, int $userId): ?array
    {
        if ($conversationId <= 0 || $userId <= 0) {
            return null;
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT c.*, l.title AS listing_title, l.id AS listing_ref_id, l.owner_id AS listing_owner_id,
                        (SELECT u.username FROM message_participants mp
                         JOIN users u ON u.id = mp.user_id
                         WHERE mp.conversation_id = c.id AND mp.user_id != ? LIMIT 1) AS other_username,
                        (SELECT mp.user_id FROM message_participants mp
                         WHERE mp.conversation_id = c.id AND mp.user_id != ? LIMIT 1) AS other_user_id
                 FROM message_conversations c
                 JOIN message_participants p ON p.conversation_id = c.id AND p.user_id = ?
                 LEFT JOIN trade_listings l ON l.id = c.listing_id
                 WHERE c.id = ?
                 LIMIT 1'
            );
            $stmt->execute([$userId, $userId, $userId, $conversationId]);
            $row = $stmt->fetch();

            return is_array($row) ? $row : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /** @return list<array<string,mixed>> */
    public function messages(int $conversationId, int $userId, int $limit = 200): array
    {
        if (!$this->isParticipant($conversationId, $userId)) {
            return [];
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT m.*, u.username AS sender_username
                 FROM messages m
                 JOIN users u ON u.id = m.sender_id
                 WHERE m.conversation_id = ?
                 ORDER BY m.id ASC
                 LIMIT ' . (int) $limit
            );
            $stmt->execute([$conversationId]);

            return $stmt->fetchAll() ?: [];
        } catch (\Throwable) {
            return [];
        }
    }

    public function send(int $conversationId, int $senderId, string $body): void
    {
        if (!$this->isParticipant($conversationId, $senderId)) {
            throw new RuntimeException('Bu sohbete mesaj gönderemezsiniz.');
        }

        $body = trim(preg_replace('/\s+/u', ' ', $body) ?? '');
        if ($body === '') {
            throw new RuntimeException('Mesaj boş olamaz.');
        }
        if (mb_strlen($body, 'UTF-8') > self::MAX_BODY_LEN) {
            throw new RuntimeException('Mesaj çok uzun (en fazla ' . self::MAX_BODY_LEN . ' karakter).');
        }

        $this->assertRateLimit($senderId);

        $now = microtime(true);
        $this->pdo->beginTransaction();
        try {
            $this->pdo->prepare(
                'INSERT INTO messages (conversation_id, sender_id, body, created_at) VALUES (?,?,?,?)'
            )->execute([$conversationId, $senderId, $body, $now]);
            $this->pdo->prepare(
                'UPDATE message_conversations SET updated_at = ? WHERE id = ?'
            )->execute([$now, $conversationId]);
            $this->pdo->commit();
        } catch (\Throwable $e) {
            $this->pdo->rollBack();
            throw $e;
        }

        $this->notifyRecipient($conversationId, $senderId, $body);
    }

    public function markRead(int $conversationId, int $userId): void
    {
        if (!$this->isParticipant($conversationId, $userId)) {
            return;
        }
        try {
            $now = microtime(true);
            $this->pdo->prepare(
                'UPDATE messages SET read_at = ?
                 WHERE conversation_id = ? AND sender_id != ? AND read_at IS NULL'
            )->execute([$now, $conversationId, $userId]);
        } catch (\Throwable) {
            // tablo yoksa atla
        }
    }

    public function unreadCount(int $userId): int
    {
        if ($userId <= 0) {
            return 0;
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT COUNT(*) FROM messages m
                 JOIN message_participants p ON p.conversation_id = m.conversation_id
                 WHERE p.user_id = ? AND m.sender_id != ? AND m.read_at IS NULL'
            );
            $stmt->execute([$userId, $userId]);

            return (int) $stmt->fetchColumn();
        } catch (\Throwable) {
            return 0;
        }
    }

    public function isParticipant(int $conversationId, int $userId): bool
    {
        if ($conversationId <= 0 || $userId <= 0) {
            return false;
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT 1 FROM message_participants WHERE conversation_id = ? AND user_id = ? LIMIT 1'
            );
            $stmt->execute([$conversationId, $userId]);

            return (bool) $stmt->fetch();
        } catch (\Throwable) {
            return false;
        }
    }

    private function findConversationId(?int $listingId, int $userA, int $userB): int
    {
        try {
            if ($listingId !== null && $listingId > 0) {
                $stmt = $this->pdo->prepare(
                    'SELECT c.id FROM message_conversations c
                     JOIN message_participants p1 ON p1.conversation_id = c.id AND p1.user_id = ?
                     JOIN message_participants p2 ON p2.conversation_id = c.id AND p2.user_id = ?
                     WHERE c.listing_id = ?
                     LIMIT 1'
                );
                $stmt->execute([$userA, $userB, $listingId]);
            } else {
                $stmt = $this->pdo->prepare(
                    'SELECT c.id FROM message_conversations c
                     JOIN message_participants p1 ON p1.conversation_id = c.id AND p1.user_id = ?
                     JOIN message_participants p2 ON p2.conversation_id = c.id AND p2.user_id = ?
                     WHERE c.listing_id IS NULL
                     LIMIT 1'
                );
                $stmt->execute([$userA, $userB]);
            }
            $val = $stmt->fetchColumn();

            return is_numeric($val) ? (int) $val : 0;
        } catch (\Throwable) {
            return 0;
        }
    }

    private function assertRateLimit(int $senderId): void
    {
        $since = microtime(true) - 60;
        $stmt = $this->pdo->prepare(
            'SELECT COUNT(*) FROM messages WHERE sender_id = ? AND created_at >= ?'
        );
        $stmt->execute([$senderId, $since]);
        if ((int) $stmt->fetchColumn() >= self::RATE_LIMIT_PER_MIN) {
            throw new RuntimeException('Çok hızlı mesaj gönderiyorsunuz. Lütfen bir dakika bekleyin.');
        }
    }

    private function notifyRecipient(int $conversationId, int $senderId, string $body): void
    {
        try {
            require_once BASE_PATH . '/app/Services/NotificationService.php';
            require_once BASE_PATH . '/app/Services/PriceDropAlertService.php';
            $stmt = $this->pdo->prepare(
                'SELECT user_id FROM message_participants WHERE conversation_id = ? AND user_id != ? LIMIT 1'
            );
            $stmt->execute([$conversationId, $senderId]);
            $recipientId = (int) $stmt->fetchColumn();
            if ($recipientId <= 0) {
                return;
            }
            $preview = mb_substr($body, 0, 120, 'UTF-8');
            if (mb_strlen($body, 'UTF-8') > 120) {
                $preview .= '…';
            }

            $listingId = 0;
            $ownerId = 0;
            try {
                $meta = $this->pdo->prepare(
                    'SELECT c.listing_id, l.owner_id
                     FROM message_conversations c
                     LEFT JOIN trade_listings l ON l.id = c.listing_id
                     WHERE c.id = ? LIMIT 1'
                );
                $meta->execute([$conversationId]);
                $row = $meta->fetch(PDO::FETCH_ASSOC);
                $listingId = (int) ($row['listing_id'] ?? 0);
                $ownerId = (int) ($row['owner_id'] ?? 0);
            } catch (\Throwable) {
                $listingId = 0;
            }

            if ($listingId > 0 && $ownerId > 0 && $senderId === $ownerId) {
                $sent = (new PriceDropAlertService())->notifySellerReply(
                    $recipientId,
                    $listingId,
                    $conversationId,
                    $preview,
                    $ownerId
                );
                if ($sent) {
                    return;
                }
            }

            if (NotificationService::existsRecent($recipientId, 'new_message', 'conversation', $conversationId, 90)) {
                return;
            }
            NotificationService::create(
                $recipientId,
                'new_message',
                'Yeni mesaj',
                $preview,
                'conversation',
                $conversationId
            );
        } catch (\Throwable) {
            // bildirim opsiyonel
        }
    }
}
