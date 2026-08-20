<?php

declare(strict_types=1);

namespace App\Services;

use App\Helpers\Auth;
use App\Helpers\Database;
use App\Helpers\Session;
use PDO;

require_once __DIR__ . '/ListingSchemaService.php';

/** Kayıtlı cep + e-posta ile şifre yenileme / kullanıcı adı hatırlatma. */
final class PasswordResetService
{
    private const SESSION_KEY = 'pwd_reset_challenge';
    private const TTL_SEC = 900;

    /**
     * @return array{id:int,username:string}|null
     */
    public static function findByPhoneAndEmail(string $phone, string $email): ?array
    {
        $email = self::normalizeEmail($email);
        $phoneKey = cx_phone_match_key($phone);
        if ($email === '' || $phoneKey === '') {
            return null;
        }

        ListingSchemaService::ensureUserColumns();
        $pdo = Database::pdo();

        $stmt = $pdo->prepare(
            'SELECT id, username, email, phone, suspended
             FROM users
             WHERE email IS NOT NULL AND LOWER(TRIM(email)) = ?
             LIMIT 20'
        );
        $stmt->execute([$email]);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC) ?: [];

        foreach ($rows as $row) {
            if ((int) ($row['suspended'] ?? 0) === 1) {
                continue;
            }
            if (cx_phone_match_key((string) ($row['phone'] ?? '')) !== $phoneKey) {
                continue;
            }

            return [
                'id' => (int) $row['id'],
                'username' => (string) $row['username'],
            ];
        }

        return null;
    }

    public static function startChallenge(int $userId, string $username): string
    {
        $token = bin2hex(random_bytes(16));
        Session::set(self::SESSION_KEY, [
            'user_id' => $userId,
            'username' => $username,
            'token' => $token,
            'expires' => time() + self::TTL_SEC,
        ]);

        return $token;
    }

    /** @return array{user_id:int,username:string,token:string}|null */
    public static function challenge(): ?array
    {
        $raw = Session::get(self::SESSION_KEY);
        if (!is_array($raw)) {
            return null;
        }
        $expires = (int) ($raw['expires'] ?? 0);
        $userId = (int) ($raw['user_id'] ?? 0);
        $username = trim((string) ($raw['username'] ?? ''));
        $token = (string) ($raw['token'] ?? '');
        if ($expires < time() || $userId <= 0 || $username === '' || $token === '') {
            self::clearChallenge();

            return null;
        }

        return [
            'user_id' => $userId,
            'username' => $username,
            'token' => $token,
        ];
    }

    public static function clearChallenge(): void
    {
        Session::forget(self::SESSION_KEY);
    }

    public static function assertChallengeToken(string $token): array
    {
        $challenge = self::challenge();
        if ($challenge === null || !hash_equals($challenge['token'], $token)) {
            self::clearChallenge();
            throw new \RuntimeException('Doğrulama süresi doldu. Cep ve e-posta ile tekrar deneyin.');
        }

        return $challenge;
    }

    public static function updatePassword(int $userId, string $password): void
    {
        if (strlen($password) < 6) {
            throw new \RuntimeException('Yeni şifre en az 6 karakter olmalı.');
        }
        $pdo = Database::pdo();
        $stmt = $pdo->prepare('SELECT id, suspended FROM users WHERE id = ? LIMIT 1');
        $stmt->execute([$userId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            throw new \RuntimeException('Hesap bulunamadı.');
        }
        if ((int) ($row['suspended'] ?? 0) === 1) {
            throw new \RuntimeException('Hesabınız askıya alınmış.');
        }

        $hash = Auth::hashPassword($password);
        $pdo->prepare('UPDATE users SET password_hash = ? WHERE id = ?')->execute([$hash, $userId]);

        try {
            $pdo->prepare('DELETE FROM sessions WHERE user_id = ?')->execute([$userId]);
        } catch (\Throwable) {
            // sessions tablosu yoksa devam
        }
    }

    public static function normalizeEmail(string $email): string
    {
        return strtolower(trim($email));
    }
}
