<?php

declare(strict_types=1);

namespace App\Helpers;

use PDOException;

final class Auth
{
    private const SESSION_TOKEN_KEY = 'changex_auth_token';

    public static function hashPassword(string $password, ?string $salt = null): string
    {
        $salt = $salt ?? bin2hex(random_bytes(16));
        $digest = hash_pbkdf2('sha256', $password, $salt, 120_000, 64, false);
        return 'pbkdf2$' . $salt . '$' . $digest;
    }

    public static function verifyPassword(string $password, string $stored): bool
    {
        if (str_starts_with($stored, 'pbkdf2$')) {
            $parts = explode('$', $stored, 3);
            if (count($parts) !== 3) {
                return false;
            }
            [, $salt, $digest] = $parts;
            $check = hash_pbkdf2('sha256', $password, $salt, 120_000, 64, false);
            return hash_equals($digest, $check);
        }
        $parts = explode('$', $stored, 2);
        if (count($parts) !== 2) {
            return false;
        }
        [$salt, $digest] = $parts;
        $check = hash('sha256', $salt . ':' . $password);
        return hash_equals($digest, $check);
    }

    public static function newSession(int $userId, int $days = 30): string
    {
        $token = rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
        $now = microtime(true);
        try {
            $pdo = Database::pdo();
            $pdo->prepare(
                'INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)'
            )->execute([$token, $userId, $now, $now + ($days * 86400)]);
        } catch (PDOException $e) {
            throw new \RuntimeException(
                'Oturum kaydı oluşturulamadı (sessions tablosu var mı? install.php çalıştırın): ' . $e->getMessage(),
                0,
                $e
            );
        }
        return $token;
    }

    public static function revokeSession(?string $token): void
    {
        if ($token === null || $token === '') {
            return;
        }
        try {
            Database::pdo()->prepare('DELETE FROM sessions WHERE token = ?')->execute([$token]);
        } catch (PDOException) {
            // ignore
        }
    }

    /** @return array<string,mixed>|null */
    public static function userFromToken(?string $token): ?array
    {
        if ($token === null || $token === '') {
            return null;
        }
        try {
            $pdo = Database::pdo();
            $hasCountry = false;
            try {
                $chk = $pdo->query('SHOW COLUMNS FROM users LIKE ' . $pdo->quote('country'));
                $hasCountry = (bool) ($chk && $chk->fetch());
            } catch (PDOException) {
                $hasCountry = false;
            }
            $cols = $hasCountry
                ? 'u.id, u.username, u.role, u.country, u.change_score, u.suspended'
                : 'u.id, u.username, u.role, u.change_score, u.suspended';
            foreach (['vip_starts_at', 'vip_ends_at'] as $vipCol) {
                try {
                    $vchk = $pdo->query('SHOW COLUMNS FROM users LIKE ' . $pdo->quote($vipCol));
                    if ($vchk && $vchk->fetch()) {
                        $cols .= ', u.' . $vipCol;
                    }
                } catch (PDOException) {
                    // kolon yok
                }
            }
            $stmt = $pdo->prepare(
                "SELECT {$cols}
                 FROM sessions s JOIN users u ON u.id = s.user_id
                 WHERE s.token = ? AND s.expires_at > ?"
            );
            $stmt->execute([$token, microtime(true)]);
            $row = $stmt->fetch();
        } catch (PDOException) {
            return null;
        }
        if (!$row) {
            return null;
        }
        if ((int) ($row['suspended'] ?? 0) === 1) {
            return null;
        }
        if (!cx_vip_can_login($row)) {
            self::revokeSession($token);
            self::clearTokenCookie();

            return null;
        }
        if (!isset($row['country'])) {
            $row['country'] = 'tr';
        }
        $row['country'] = cx_normalize_country((string) $row['country']);

        return $row;
    }

    public static function tokenFromRequest(): ?string
    {
        $sessionToken = Session::get(self::SESSION_TOKEN_KEY);
        if (is_string($sessionToken) && $sessionToken !== '') {
            return $sessionToken;
        }
        if (!empty($_COOKIE['changex_token'])) {
            return (string) $_COOKIE['changex_token'];
        }
        $hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        if (str_starts_with(strtolower($hdr), 'bearer ')) {
            return trim(substr($hdr, 7));
        }
        return null;
    }

    public static function setTokenCookie(string $token, int $days = 30): void
    {
        Session::set(self::SESSION_TOKEN_KEY, $token);

        if (headers_sent()) {
            return;
        }

        setcookie('changex_token', $token, [
            'expires' => time() + ($days * 86400),
            'path' => '/',
            'httponly' => true,
            'samesite' => 'Lax',
            'secure' => Session::isHttps(),
        ]);
    }

    public static function clearTokenCookie(): void
    {
        Session::forget(self::SESSION_TOKEN_KEY);
        if (!headers_sent()) {
            setcookie('changex_token', '', [
                'expires' => time() - 3600,
                'path' => '/',
                'httponly' => true,
                'samesite' => 'Lax',
                'secure' => Session::isHttps(),
            ]);
        }
    }
}
