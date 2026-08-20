<?php

declare(strict_types=1);

/**
 * CLI: Car.gr tarzi cesitli marka/model ilanlari mevcut kullanicilara dagitir.
 * Kullanim: php scripts/seed_cargr_diverse.php
 */

$root = dirname(__DIR__) . '/php-site';
require $root . '/bootstrap.php';
cx_bootstrap(false);
App\Helpers\Database::connect(cx_load_db_config());

require_once $root . '/app/Services/CarGrDiverseSeedService.php';

foreach (App\Services\CarGrDiverseSeedService::seed() as $line) {
    echo $line, PHP_EOL;
}
