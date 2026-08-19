<?php

/**
 * GET    /api/v1/user/notifications          — bildirim listesi
 * POST   /api/v1/user/notifications/read     — tümünü okundu işaretle
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Database;

api_method('GET', 'POST');
$user = api_require_auth();
$uid  = (int) $user['id'];
$pdo  = Database::pdo();

$method = strtoupper($_SERVER['REQUEST_METHOD']);

// Tablo var mı kontrol et
try {
    $pdo->query('SELECT 1 FROM notifications LIMIT 1');
} catch (Throwable) {
    // Tablo yoksa boş dön
    api_ok(['items' => [], 'unread' => 0]);
}

if ($method === 'POST') {
    // Tümünü okundu işaretle
    try {
        $pdo->prepare('UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL')
            ->execute([microtime(true), $uid]);
    } catch (Throwable) {}
    api_ok(['marked_read' => true]);
}

// GET
$stmt = $pdo->prepare(
    'SELECT id, type, title, body, link, read_at, created_at
     FROM notifications
     WHERE user_id = ?
     ORDER BY created_at DESC
     LIMIT 100'
);
$stmt->execute([$uid]);
$rows   = $stmt->fetchAll();
$unread = 0;
$items  = array_map(static function (array $n) use (&$unread): array {
    if ($n['read_at'] === null) {
        $unread++;
    }
    return [
        'id'         => (int) $n['id'],
        'type'       => $n['type'] ?? 'info',
        'title'      => $n['title'] ?? '',
        'body'       => $n['body'] ?? '',
        'link'       => $n['link'] ?? null,
        'read'       => $n['read_at'] !== null,
        'created_at' => $n['created_at'],
    ];
}, $rows);

api_ok(['items' => $items, 'unread' => $unread]);
