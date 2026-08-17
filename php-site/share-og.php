<?php

declare(strict_types=1);

define('CX_SKIP_SESSION', true);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingService.php';
require_once __DIR__ . '/app/Services/ShareOgImageService.php';

use App\Services\ListingService;
use App\Services\ShareOgImageService;

cx_bootstrap();

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$id = (int) ($_GET['id'] ?? 0);

if ($id <= 0) {
    http_response_code(404);
    exit;
}

$svc = new ListingService($base);
$item = $svc->findById($id);

if ($item === null || !cx_listing_is_public((string) ($item['status'] ?? ''))) {
    http_response_code(404);
    exit;
}

try {
    $path = ShareOgImageService::ensure($item, $app);
} catch (Throwable $e) {
    http_response_code(503);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Gorsel uretilemedi.';
    exit;
}

if (!is_file($path)) {
    http_response_code(404);
    exit;
}

$staticUrl = ShareOgImageService::publicUrl($path, $app);
if (!headers_sent()) {
    header('Location: ' . $staticUrl, true, 302);
    header('Cache-Control: public, max-age=86400');
}
exit;
