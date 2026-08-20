<?php
declare(strict_types=1);

/** @var array<string,mixed> $cfg */
$cfg = require __DIR__ . '/config/app.php';
if (!empty($cfg['production'])) {
    http_response_code(404);
    exit;
}

header('Content-Type: text/plain; charset=utf-8');
echo "BenimBazar OK\n";
