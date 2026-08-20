<?php
/**
 * Canli guncelleme alici — config/deploy.local.php gerekli.
 * FTP docroot uyusmazsa deploy_live_php.py bu endpoint'i kullanir.
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST only']);
    exit;
}

$configPath = __DIR__ . '/config/deploy.local.php';
if (!is_file($configPath)) {
    http_response_code(503);
    echo json_encode(['ok' => false, 'error' => 'deploy.local.php yok']);
    exit;
}

/** @var array<string,mixed> $cfg */
$cfg = require $configPath;
$secret = (string) ($cfg['secret'] ?? '');
if ($secret === '' || !hash_equals($secret, (string) ($_POST['secret'] ?? ''))) {
    http_response_code(403);
    echo json_encode(['ok' => false, 'error' => 'secret']);
    exit;
}

$rel = str_replace('\\', '/', (string) ($_POST['path'] ?? ''));
$rel = ltrim($rel, '/');
if ($rel === '' || str_contains($rel, '..') || str_starts_with($rel, 'config/')) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'invalid path']);
    exit;
}

$blocked = ['config/database.php', 'config/database.local.php', 'config/google.local.php', 'config/deploy.local.php'];
if (in_array($rel, $blocked, true)) {
    http_response_code(403);
    echo json_encode(['ok' => false, 'error' => 'blocked path']);
    exit;
}

$content = base64_decode((string) ($_POST['content_b64'] ?? ''), true);
if ($content === false) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'bad content']);
    exit;
}

$target = __DIR__ . '/' . $rel;
$dir = dirname($target);
if (!is_dir($dir)) {
    mkdir($dir, 0755, true);
}

if (file_put_contents($target, $content) === false) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'write failed']);
    exit;
}

echo json_encode(['ok' => true, 'path' => $rel, 'bytes' => strlen($content)]);
