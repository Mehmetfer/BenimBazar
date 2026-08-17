<?php

declare(strict_types=1);

namespace App\Helpers;

final class Session
{
    public static function start(array $config): void
    {
        if (session_status() === PHP_SESSION_ACTIVE) {
            return;
        }

        $lifetime = (int) ($config['session_lifetime'] ?? 86400);
        ini_set('session.gc_maxlifetime', (string) $lifetime);

        $savePath = $config['session_save_path'] ?? '';
        if ($savePath !== '') {
            if (!is_dir($savePath)) {
                mkdir($savePath, 0755, true);
            }
            if (is_writable($savePath)) {
                session_save_path($savePath);
            }
        }

        session_name($config['session_name'] ?? 'changex_session');
        session_set_cookie_params([
            'lifetime' => $lifetime,
            'path' => $config['session_path'] ?? '/',
            'domain' => $config['session_domain'] ?? '',
            'secure' => $config['session_secure'] ?? self::isHttps(),
            'httponly' => true,
            'samesite' => $config['session_samesite'] ?? 'Lax',
        ]);
        session_start();
    }

    public static function isHttps(): bool
    {
        if (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') {
            return true;
        }
        if (!empty($_SERVER['HTTP_X_FORWARDED_PROTO'])
            && strtolower((string) $_SERVER['HTTP_X_FORWARDED_PROTO']) === 'https') {
            return true;
        }
        return !empty($_SERVER['SERVER_PORT']) && (int) $_SERVER['SERVER_PORT'] === 443;
    }

    public static function set(string $key, mixed $value): void
    {
        $_SESSION[$key] = $value;
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        return $_SESSION[$key] ?? $default;
    }

    public static function forget(string $key): void
    {
        unset($_SESSION[$key]);
    }
}
