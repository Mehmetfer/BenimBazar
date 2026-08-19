<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Database;
use PDO;
use Throwable;

/** v4 sema: goruntulenme, sureli ilan, bildirimler (idempotent). */
final class ListingSchemaService
{
    public static function ensure(): void
    {
        static $done = false;

        try {
            $pdo = Database::pdo();
            if (!$done) {
                $done = true;
                $needsV4 = !self::columnExists($pdo, 'trade_listings', 'view_count')
                    || !self::columnExists($pdo, 'trade_listings', 'published_at')
                    || !self::columnExists($pdo, 'trade_listings', 'expires_at');
                if ($needsV4) {
                    self::applyV4($pdo);
                } else {
                    self::ensureAuxTables($pdo);
                }
            }
            // Her cagrida (idempotent): country/phone/city
            self::ensureUserProfileColumns($pdo);
            self::ensurePriceHistory($pdo);
        } catch (Throwable) {
            // Kurulum / migrate
        }
    }

    /** Kayit oncesi zorunlu cagirin. */
    public static function ensureUserColumns(): void
    {
        self::ensureUserProfileColumns(Database::pdo());
    }

    public static function ensureUserProfileColumns(PDO $pdo): void
    {
        $columns = [
            'country' => "VARCHAR(8) NOT NULL DEFAULT 'tr'",
            'phone' => 'VARCHAR(32) NULL DEFAULT NULL',
            'phone_verified_at' => 'DOUBLE NULL DEFAULT NULL',
            'city' => 'VARCHAR(128) NULL DEFAULT NULL',
            'gallery_name' => 'VARCHAR(128) NULL DEFAULT NULL',
            'website' => 'VARCHAR(255) NULL DEFAULT NULL',
            'about' => 'VARCHAR(500) NULL DEFAULT NULL',
            'avatar_url' => 'VARCHAR(512) NULL DEFAULT NULL',
            'gallery_banner' => 'VARCHAR(512) NULL DEFAULT NULL',
            'google_id' => 'VARCHAR(128) NULL DEFAULT NULL',
            'email' => 'VARCHAR(255) NULL DEFAULT NULL',
            'vip_starts_at' => 'DATE NULL DEFAULT NULL',
            'vip_ends_at' => 'DATE NULL DEFAULT NULL',
            'gallery_hours' => 'TEXT NULL DEFAULT NULL',
        ];
        foreach ($columns as $column => $definition) {
            if (self::columnExists($pdo, 'users', $column)) {
                continue;
            }
            $col = str_replace('`', '', $column);
            $attempts = [
                "ALTER TABLE users ADD COLUMN `{$col}` {$definition}",
                "ALTER TABLE `users` ADD `{$col}` {$definition}",
            ];
            $ok = false;
            $last = null;
            foreach ($attempts as $sql) {
                try {
                    $pdo->exec($sql);
                    $ok = true;
                    break;
                } catch (Throwable $e) {
                    $last = $e;
                }
            }
            if (!$ok && $last !== null && !self::columnExists($pdo, 'users', $column)) {
                throw new \RuntimeException(
                    "users.{$column} kolonu eklenemedi: " . $last->getMessage()
                );
            }
        }
    }

    private static function ensureAuxTables(PDO $pdo): void
    {
        self::ensureNotificationsTable($pdo);
        try {
            SocialService::ensureTables();
        } catch (Throwable) {
            // favoriler opsiyonel
        }
    }

    private static function ensureNotificationsTable(PDO $pdo): void
    {
        try {
            $pdo->exec(
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
        } catch (Throwable) {
            // bildirimler opsiyonel
        }
    }

    private static function applyV4(PDO $pdo): void
    {
        $columns = [
            'view_count' => 'INT UNSIGNED NOT NULL DEFAULT 0',
            'published_at' => 'DOUBLE NULL',
            'expires_at' => 'DOUBLE NULL',
            'sold_at' => 'DOUBLE NULL',
        ];
        foreach ($columns as $column => $definition) {
            if (self::columnExists($pdo, 'trade_listings', $column)) {
                continue;
            }
            try {
                $pdo->exec(
                    'ALTER TABLE trade_listings ADD COLUMN `' . str_replace('`', '', $column) . '` ' . $definition
                );
            } catch (Throwable) {
                // duplicate / yetki
            }
        }

        $file = dirname(__DIR__, 2) . '/database/migrate-v4.sql';
        if (is_file($file)) {
            $sql = (string) file_get_contents($file);
            foreach (self::splitStatements($sql) as $stmt) {
                if ($stmt === '' || stripos($stmt, 'ALTER TABLE trade_listings') === 0) {
                    continue;
                }
                try {
                    $pdo->exec($stmt);
                } catch (Throwable) {
                    // CREATE IF NOT EXISTS vb.
                }
            }
        }

        try {
            SocialService::ensureTables();
        } catch (Throwable) {
            // listing_favorites
        }

        self::ensurePriceDropAlerts($pdo);
        self::ensurePriceHistory($pdo);

        self::ensureNotificationsTable($pdo);

        try {
            self::backfillPublishedDates($pdo);
        } catch (Throwable) {
            // backfill opsiyonel
        }
    }

    public static function ensurePriceDropAlerts(?PDO $pdo = null): void
    {
        $pdo = $pdo ?? Database::pdo();
        foreach ([
            'alert_enabled' => 'TINYINT(1) NOT NULL DEFAULT 1',
            'price_currency' => 'VARCHAR(8) NULL',
            'price_amount' => 'DECIMAL(14,2) NULL',
        ] as $col => $def) {
            if (!self::columnExists($pdo, 'listing_favorites', $col)) {
                try {
                    $pdo->exec("ALTER TABLE listing_favorites ADD COLUMN `{$col}` {$def}");
                } catch (Throwable) {
                    // yetki / duplicate
                }
            }
        }

        try {
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS listing_price_drop_pending (
                  listing_id INT UNSIGNED NOT NULL,
                  old_currency VARCHAR(8) NOT NULL,
                  old_amount DECIMAL(14,2) NOT NULL,
                  new_currency VARCHAR(8) NOT NULL,
                  new_amount DECIMAL(14,2) NOT NULL,
                  old_photo_count INT UNSIGNED NOT NULL DEFAULT 0,
                  new_photo_count INT UNSIGNED NOT NULL DEFAULT 0,
                  created_at DOUBLE NOT NULL,
                  PRIMARY KEY (listing_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
            );
        } catch (Throwable) {
            // yetki
        }

        foreach ([
            'old_photo_count' => 'INT UNSIGNED NOT NULL DEFAULT 0',
            'new_photo_count' => 'INT UNSIGNED NOT NULL DEFAULT 0',
        ] as $col => $def) {
            if (!self::columnExists($pdo, 'listing_price_drop_pending', $col)) {
                try {
                    $pdo->exec("ALTER TABLE listing_price_drop_pending ADD COLUMN `{$col}` {$def}");
                } catch (Throwable) {
                    // yetki / duplicate
                }
            }
        }
    }

    public static function ensurePriceHistory(?PDO $pdo = null): void
    {
        $pdo = $pdo ?? Database::pdo();
        try {
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS listing_price_history (
                  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                  listing_id INT UNSIGNED NOT NULL,
                  currency VARCHAR(8) NOT NULL,
                  amount DECIMAL(14,2) NOT NULL,
                  created_at DOUBLE NOT NULL,
                  PRIMARY KEY (id),
                  KEY idx_lph_listing_created (listing_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
            );
        } catch (Throwable) {
            // yetki
        }
    }

    private static function backfillPublishedDates(PDO $pdo): void
    {
        if (!self::columnExists($pdo, 'trade_listings', 'published_at')) {
            return;
        }
        $ttl = cx_listing_ttl_days();
        $now = microtime(true);
        $pdo->exec(
            "UPDATE trade_listings
             SET published_at = created_at,
                 expires_at = created_at + " . ($ttl * 86400) . "
             WHERE published_at IS NULL
               AND UPPER(COALESCE(status,'')) IN ('APPROVED','ACTIVE')"
        );
    }

    /** @return list<string> */
    private static function splitStatements(string $sql): array
    {
        $parts = preg_split('/;\s*\n/', $sql) ?: [];

        return array_map(static fn (string $s): string => trim($s), $parts);
    }

    private static function columnExists(PDO $pdo, string $table, string $column): bool
    {
        $table = preg_replace('/[^a-zA-Z0-9_]/', '', $table) ?? '';
        $column = preg_replace('/[^a-zA-Z0-9_]/', '', $column) ?? '';
        if ($table === '' || $column === '') {
            return false;
        }
        try {
            // MariaDB: SHOW ... LIKE ? prepared desteklemez
            $sql = 'SHOW COLUMNS FROM `' . $table . '` LIKE ' . $pdo->quote($column);
            $stmt = $pdo->query($sql);

            return (bool) ($stmt && $stmt->fetch());
        } catch (Throwable) {
            return false;
        }
    }
}
