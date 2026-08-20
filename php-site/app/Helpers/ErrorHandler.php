<?php

declare(strict_types=1);

namespace App\Helpers;

use ErrorException;
use Throwable;

/** Uretimde 500 yerine kontrollu yanit + log. */
final class ErrorHandler
{
    private static bool $registered = false;
    private static bool $responding = false;

    public static function register(): void
    {
        if (self::$registered) {
            return;
        }
        self::$registered = true;

        $debug = self::debugMode();
        ini_set('display_errors', $debug ? '1' : '0');
        ini_set('log_errors', '1');
        error_reporting(E_ALL);

        set_exception_handler([self::class, 'handleException']);
        set_error_handler([self::class, 'handleError']);
        register_shutdown_function([self::class, 'handleShutdown']);
    }

    public static function handleException(Throwable $e): void
    {
        if (self::$responding) {
            return;
        }
        self::$responding = true;
        self::log($e);
        self::respond($e);
    }

    public static function handleError(int $severity, string $message, string $file, int $line): bool
    {
        if (!(error_reporting() & $severity)) {
            return false;
        }
        if (in_array($severity, [E_NOTICE, E_USER_NOTICE, E_DEPRECATED, E_USER_DEPRECATED], true)) {
            self::logMessage($message, $file, $line, $severity);

            return true;
        }
        throw new ErrorException($message, 0, $severity, $file, $line);
    }

    public static function handleShutdown(): void
    {
        if (self::$responding) {
            return;
        }
        $err = error_get_last();
        if ($err === null) {
            return;
        }
        $fatal = [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR, E_USER_ERROR];
        if (!in_array($err['type'], $fatal, true)) {
            return;
        }
        self::handleException(new ErrorException(
            (string) $err['message'],
            0,
            (int) $err['type'],
            (string) $err['file'],
            (int) $err['line']
        ));
    }

    /** Guvenli sayfa calistirma — yakalanmamis hatalari 500 yerine 503/JSON yapar. */
    public static function run(callable $fn): void
    {
        try {
            $fn();
        } catch (Throwable $e) {
            self::handleException($e);
        }
    }

    private static function debugMode(): bool
    {
        if (defined('CX_DEBUG') && CX_DEBUG) {
            return true;
        }
        $path = BASE_PATH . '/config/app.php';
        if (!is_file($path)) {
            return false;
        }
        /** @var array<string,mixed> $cfg */
        $cfg = require $path;

        return !empty($cfg['debug']) && empty($cfg['production']);
    }

    private static function log(Throwable $e): void
    {
        self::logMessage($e->getMessage(), $e->getFile(), $e->getLine(), $e->getCode(), $e);
    }

    private static function logMessage(
        string $message,
        string $file,
        int $line,
        int $code = 0,
        ?Throwable $e = null
    ): void {
        $dir = BASE_PATH . '/storage/logs';
        if (!is_dir($dir)) {
            @mkdir($dir, 0755, true);
        }
        $lineOut = date('c') . ' [' . $code . '] ' . $message . ' @ ' . $file . ':' . $line;
        if ($e !== null) {
            $lineOut .= "\n" . $e->getTraceAsString();
        }
        $lineOut .= "\n---\n";
        @file_put_contents($dir . '/php-errors.log', $lineOut, FILE_APPEND | LOCK_EX);
        @error_log('[BenimBazar] ' . $message);
    }

    private static function respond(Throwable $e): void
    {
        if (headers_sent()) {
            echo self::debugMode()
                ? "\n<!-- " . htmlspecialchars($e->getMessage(), ENT_QUOTES, 'UTF-8') . " -->"
                : "\n<!-- gecici sorun -->";

            return;
        }

        $debug = self::debugMode();
        $publicMsg = self::publicMessage($e);
        $status = 503;

        if (self::wantsJson()) {
            header('Content-Type: application/json; charset=UTF-8');
            http_response_code($status);
            echo json_encode([
                'ok' => false,
                'error' => $publicMsg,
                'detail' => $debug ? $e->getMessage() : null,
            ], JSON_UNESCAPED_UNICODE);

            return;
        }

        http_response_code($status);
        header('Content-Type: text/html; charset=UTF-8');
        header('Cache-Control: no-store');

        $title = 'Gecici sorun';
        $hint = 'Sayfa yenilenebilir veya birkac dakika sonra tekrar denenebilir.';
        if ($debug) {
            $hint = $e->getMessage() . ' — ' . $e->getFile() . ':' . (int) $e->getLine();
        }

        $view = BASE_PATH . '/views/error.php';
        if (is_file($view)) {
            require $view;

            return;
        }

        echo '<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8"><title>'
            . htmlspecialchars($title, ENT_QUOTES, 'UTF-8')
            . '</title></head><body style="font-family:sans-serif;background:#0d0f14;color:#f5f5f5;padding:2rem">'
            . '<h1>' . htmlspecialchars($title, ENT_QUOTES, 'UTF-8') . '</h1>'
            . '<p>' . htmlspecialchars($publicMsg, ENT_QUOTES, 'UTF-8') . '</p>'
            . '<p style="opacity:.75">' . $hint . '</p>'
            . '<p><a href="/index.php" style="color:#d4af37">Ana sayfaya don</a></p></body></html>';
    }

    private static function publicMessage(Throwable $e): string
    {
        $msg = $e->getMessage();
        if (str_contains($msg, '1045') || str_contains($msg, 'Access denied')) {
            return 'Veritabani baglantisi gecici olarak kullanilamiyor.';
        }
        if (str_contains($msg, 'Veritabani') || str_contains($msg, 'Veritabanı') || str_contains($msg, 'Database')) {
            return 'Veritabani islemi su an tamamlanamadi.';
        }
        if ($e instanceof ErrorException) {
            return 'Islem sirasinda beklenmeyen bir sorun olustu.';
        }

        return 'Gecici bir sorun olustu. Lutfen tekrar deneyin.';
    }

    private static function wantsJson(): bool
    {
        $accept = (string) ($_SERVER['HTTP_ACCEPT'] ?? '');
        if (str_contains($accept, 'application/json')) {
            return true;
        }
        $script = basename((string) ($_SERVER['SCRIPT_NAME'] ?? ''));
        if (in_array($script, ['deploy-hook.php', 'listing-publish-stats.php'], true)) {
            return true;
        }

        return isset($_POST['islem']) || isset($_GET['format']) && $_GET['format'] === 'json';
    }
}
