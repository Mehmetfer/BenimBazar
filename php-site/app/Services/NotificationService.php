<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;

/** Site ici bildirimler + opsiyonel e-posta. */
final class NotificationService
{
    private PDO $pdo;

    public function __construct()
    {
        $this->pdo = Database::pdo();
        self::ensureTable();
    }

    public static function ensureTable(): void
    {
        try {
            Database::pdo()->exec(
                'CREATE TABLE IF NOT EXISTS user_notifications (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  user_id INT UNSIGNED NOT NULL,
                  type VARCHAR(64) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  body TEXT NOT NULL,
                  entity_type VARCHAR(64) NOT NULL DEFAULT \'\',
                  entity_id INT UNSIGNED NOT NULL DEFAULT 0,
                  read_at DOUBLE NULL,
                  created_at DOUBLE NOT NULL,
                  PRIMARY KEY (id),
                  KEY idx_un_user_read (user_id, read_at),
                  KEY idx_un_user_created (user_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
        } catch (\Throwable) {
            // yetki / eski MySQL
        }
    }

    public static function create(
        int $userId,
        string $type,
        string $title,
        string $body,
        string $entityType = '',
        int $entityId = 0,
        bool $sendEmail = false
    ): void {
        if ($userId <= 0) {
            return;
        }
        $title = trim($title);
        $body = rtrim($body);
        // Her bildirim metninin sonuna dua emojisi
        if ($body !== '' && !str_ends_with($body, '🤲')) {
            $body .= "\n\n🤲";
        } elseif ($body === '') {
            $body = '🤲';
        }
        try {
            $pdo = Database::pdo();
            $now = microtime(true);
            $pdo->prepare(
                'INSERT INTO user_notifications (user_id, type, title, body, entity_type, entity_id, created_at)
                 VALUES (?,?,?,?,?,?,?)'
            )->execute([$userId, $type, $title, $body, $entityType, $entityId, $now]);

            if ($sendEmail) {
                self::maybeSendEmail($userId, $title, $body);
            }
        } catch (\Throwable) {
            // tablo yoksa atla
        }
    }

    public static function existsRecent(
        int $userId,
        string $type,
        string $entityType,
        int $entityId,
        int $withinSeconds
    ): bool {
        try {
            $pdo = Database::pdo();
            $since = microtime(true) - $withinSeconds;
            $stmt = $pdo->prepare(
                'SELECT id FROM user_notifications
                 WHERE user_id = ? AND type = ? AND entity_type = ? AND entity_id = ? AND created_at >= ?
                 LIMIT 1'
            );
            $stmt->execute([$userId, $type, $entityType, $entityId, $since]);

            return (bool) $stmt->fetch();
        } catch (\Throwable) {
            return false;
        }
    }

    public function unreadCount(int $userId): int
    {
        if ($userId <= 0) {
            return 0;
        }
        try {
            $stmt = $this->pdo->prepare(
                'SELECT COUNT(*) FROM user_notifications WHERE user_id = ? AND read_at IS NULL'
            );
            $stmt->execute([$userId]);

            return (int) $stmt->fetchColumn();
        } catch (\Throwable) {
            return 0;
        }
    }

    /** @return list<array<string,mixed>> */
    public function listForUser(int $userId, int $limit = 40): array
    {
        try {
            self::ensureTable();
            $stmt = $this->pdo->prepare(
                'SELECT * FROM user_notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ' . (int) $limit
            );
            $stmt->execute([$userId]);

            return $stmt->fetchAll() ?: [];
        } catch (\Throwable) {
            return [];
        }
    }

    public function markRead(int $notificationId, int $userId): void
    {
        try {
            self::ensureTable();
            $this->pdo->prepare(
                'UPDATE user_notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL'
            )->execute([microtime(true), $notificationId, $userId]);
        } catch (\Throwable) {
            // tablo yoksa atla
        }
    }

    public function markAllRead(int $userId): void
    {
        try {
            self::ensureTable();
            $this->pdo->prepare(
                'UPDATE user_notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL'
            )->execute([microtime(true), $userId]);
        } catch (\Throwable) {
            // tablo yoksa atla
        }
    }

    private static function maybeSendEmail(int $userId, string $title, string $body): void
    {
        try {
            $pdo = Database::pdo();
            $stmt = $pdo->prepare('SELECT email FROM users WHERE id = ? LIMIT 1');
            $stmt->execute([$userId]);
            $email = trim((string) $stmt->fetchColumn());
            if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
                return;
            }
            $site = cx_site_name();
            $headers = 'Content-Type: text/plain; charset=UTF-8' . "\r\n"
                . 'From: ' . $site . ' <noreply@changex.local>' . "\r\n";
            @mail($email, '[' . $site . '] ' . $title, $body . "\n\n— " . $site, $headers);
        } catch (\Throwable) {
            // e-posta opsiyonel
        }
    }
}
