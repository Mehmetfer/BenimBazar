<?php

declare(strict_types=1);

/** PHP 7.4 uyumluluk (Natro eski sürüm seçiliyse). */
if (!function_exists('str_starts_with')) {
    function str_starts_with(string $haystack, string $needle): bool
    {
        return $needle === '' || strncmp($haystack, $needle, strlen($needle)) === 0;
    }
}

if (!function_exists('str_ends_with')) {
    function str_ends_with(string $haystack, string $needle): bool
    {
        if ($needle === '') {
            return true;
        }
        $len = strlen($needle);
        return substr($haystack, -$len) === $needle;
    }
}

define('BASE_PATH', __DIR__);

require_once __DIR__ . '/app/Helpers/ErrorHandler.php';

use App\Helpers\ErrorHandler;

ErrorHandler::register();

spl_autoload_register(static function (string $class): void {
    if (!str_starts_with($class, 'App\\')) {
        return;
    }
    $rel = 'app/' . str_replace('\\', '/', substr($class, 4)) . '.php';
    $path = BASE_PATH . '/' . $rel;
    if (is_file($path)) {
        require_once $path;
    }
});

require_once __DIR__ . '/app/Helpers/Database.php';
require_once __DIR__ . '/app/Helpers/Session.php';
require_once __DIR__ . '/app/Helpers/Auth.php';
require_once __DIR__ . '/app/Helpers/helpers.php';
require_once __DIR__ . '/app/Helpers/categories.php';
require_once __DIR__ . '/app/Helpers/vehicle-filters.php';
require_once __DIR__ . '/app/Helpers/vehicle-brands.php';
require_once __DIR__ . '/app/Helpers/listing-similar.php';
require_once __DIR__ . '/app/Helpers/vehicle-commercial.php';
require_once __DIR__ . '/app/Helpers/vehicle-model-catalog-data.php';
require_once __DIR__ . '/app/Helpers/vehicle-models.php';

require_once __DIR__ . '/app/Helpers/Security.php';

use App\Helpers\Auth;
use App\Helpers\Database;
use App\Helpers\Security;
use App\Helpers\Session;

/** @return array<string,mixed> */
function cx_app_config(): array
{
    static $cfg = null;
    if ($cfg === null) {
        $cfg = require BASE_PATH . '/config/app.php';
    }
    return $cfg;
}

function cx_load_db_config(): array
{
    $mainPath = BASE_PATH . '/config/database.php';
    if (!is_file($mainPath)) {
        throw new RuntimeException('config/database.php bulunamadi');
    }
    /** @var array<string,mixed> $cfg */
    $cfg = require $mainPath;
    $localPath = BASE_PATH . '/config/database.local.php';
    if (is_file($localPath)) {
        /** @var array<string,mixed> $local */
        $local = require $localPath;
        $cfg = array_merge($cfg, $local);
    }
    $pass = (string) ($cfg['password'] ?? '');
    if ($pass === '' || $pass === 'BURAYA_MYSQL_SIFRENIZI_YAZIN' || $pass === 'MYSQL_SIFRENIZ_BURAYA') {
        throw new RuntimeException(
            'MySQL sifresi ayarlanmamis. config/database.local.php olusturun '
            . '(ornek: config/database.local.php.example) veya database.php icinde password yazin.'
        );
    }
    return $cfg;
}

/** @deprecated use cx_load_db_config() */
function cx_db_config_file(): string
{
    return BASE_PATH . '/config/database.php';
}

function cx_bootstrap(bool $needDb = true): void
{
    $app = cx_app_config();
    date_default_timezone_set($app['timezone'] ?? 'Europe/Istanbul');
    if (function_exists('mb_internal_encoding')) {
        mb_internal_encoding('UTF-8');
    }

    if (!defined('CX_SKIP_SESSION') && session_status() !== PHP_SESSION_ACTIVE) {
        Session::start($app);
    }

    Security::sendHeaders();

    if ($needDb) {
        try {
            Database::connect(cx_load_db_config());
            try {
                \App\Services\ListingSchemaService::ensure();
            } catch (Throwable) {
                // sema opsiyonel
            }
        } catch (Throwable $e) {
            if (!is_file(BASE_PATH . '/storage/installed.lock')) {
                if (!headers_sent()) {
                    header('Location: /kurulum.php');
                }
                exit;
            }
            ErrorHandler::handleException($e);
        }
    }
}

/** @return array<string,mixed>|null */
function cx_current_user(): ?array
{
    return Auth::userFromToken(Auth::tokenFromRequest());
}

function cx_require_user(?string $next = null): array
{
    $u = cx_current_user();
    if ($u === null) {
        cx_flash('error', 'Giriş yapmanız gerekiyor.');
        $url = '/login.php';
        if ($next !== null && $next !== '') {
            $url .= '?next=' . urlencode(cx_safe_next($next));
        }
        cx_redirect($url);
    }
    return $u;
}
