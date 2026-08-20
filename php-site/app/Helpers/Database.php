<?php

declare(strict_types=1);

namespace App\Helpers;

use PDO;
use PDOException;
use RuntimeException;

/** Soyağacı (SoyKutugu) ile aynı PDO singleton — cPanel MySQL. */
final class Database
{
    private static ?PDO $pdo = null;

    public static function connect(array $config): PDO
    {
        if (self::$pdo instanceof PDO) {
            return self::$pdo;
        }

        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=%s',
            $config['host'],
            (int) $config['port'],
            $config['database'],
            $config['charset'] ?? 'utf8mb4'
        );

        try {
            self::$pdo = new PDO($dsn, $config['username'], $config['password'], [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]);
        } catch (PDOException $e) {
            $msg = $e->getMessage();
            if (str_contains($msg, '1045') || str_contains($msg, 'Access denied')) {
                throw new RuntimeException(
                    'MySQL kullanici/sifre hatali (1045). cPanel -> config/database.local.php '
                    . 'veya database.php icinde sifreyi kontrol edin.',
                    0,
                    $e
                );
            }
            throw new RuntimeException('Veritabanı bağlantısı kurulamadı: ' . $msg, 0, $e);
        }

        return self::$pdo;
    }

    public static function pdo(): PDO
    {
        if (!self::$pdo instanceof PDO) {
            throw new RuntimeException('Veritabanı bağlantısı henüz kurulmadı.');
        }

        return self::$pdo;
    }
}
