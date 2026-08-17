<?php

declare(strict_types=1);

namespace App\Helpers;

final class Security
{
    public static function sendHeaders(): void
    {
        if (headers_sent()) {
            return;
        }
        header('X-Frame-Options: SAMEORIGIN');
        header('X-Content-Type-Options: nosniff');
        header('Referrer-Policy: strict-origin-when-cross-origin');
        header('Permissions-Policy: geolocation=(), microphone=(), camera=()');
        if (Session::isHttps()) {
            header('Strict-Transport-Security: max-age=31536000; includeSubDomains');
        }
    }

    public static function csrfToken(): string
    {
        if (session_status() !== PHP_SESSION_ACTIVE) {
            @session_start();
        }
        $token = $_SESSION['_csrf'] ?? null;
        if (!is_string($token) || strlen($token) < 32) {
            $token = bin2hex(random_bytes(32));
            $_SESSION['_csrf'] = $token;
        }
        return $token;
    }

    public static function csrfField(): string
    {
        $t = self::csrfToken();
        return '<input type="hidden" name="_csrf" value="' . htmlspecialchars($t, ENT_QUOTES, 'UTF-8') . '">';
    }

    public static function verifyCsrf(?string $token): bool
    {
        if ($token === null || $token === '') {
            return false;
        }
        $expected = $_SESSION['_csrf'] ?? '';
        return is_string($expected) && hash_equals($expected, $token);
    }

    public static function requireCsrf(): void
    {
        $token = $_POST['_csrf'] ?? $_SERVER['HTTP_X_CSRF_TOKEN'] ?? null;
        if (!self::verifyCsrf(is_string($token) ? $token : null)) {
            http_response_code(403);
            exit('CSRF dogrulamasi basarisiz. Sayfayi yenileyip tekrar deneyin.');
        }
    }

    /** Basit IP+endpoint rate limit (storage/rate/*.json) */
    public static function rateLimit(string $endpoint, int $max = 30, int $windowSec = 60): void
    {
        $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '0');
        $key = preg_replace('/[^a-z0-9_-]/i', '_', $endpoint) ?? 'default';
        $dir = BASE_PATH . '/storage/rate';
        if (!is_dir($dir)) {
            @mkdir($dir, 0755, true);
        }
        $file = $dir . '/' . sha1($ip . '|' . $key) . '.json';
        $now = time();
        $data = ['t' => $now, 'c' => 0];
        if (is_file($file)) {
            $raw = json_decode((string) file_get_contents($file), true);
            if (is_array($raw)) {
                $data = $raw;
            }
        }
        if (($now - (int) ($data['t'] ?? 0)) >= $windowSec) {
            $data = ['t' => $now, 'c' => 0];
        }
        $data['c'] = (int) ($data['c'] ?? 0) + 1;
        file_put_contents($file, json_encode($data));
        if ($data['c'] > $max) {
            http_response_code(429);
            exit('Cok fazla istek. Lutfen bir dakika bekleyin.');
        }
    }
}
