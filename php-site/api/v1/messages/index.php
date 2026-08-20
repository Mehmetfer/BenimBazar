<?php

/**
 * GET  /api/v1/messages              — konuşma listesi
 * GET  /api/v1/messages?conv=<id>    — konuşma detayı (mesajlar)
 * POST /api/v1/messages              — mesaj gönder
 *
 * POST body: { conversation_id: X, body: "..." }
 *   veya yeni konuşma: { listing_id: X, body: "..." }
 */

declare(strict_types=1);

require_once dirname(__DIR__, 3) . '/api/bootstrap.php';

use App\Helpers\Database;
use App\Helpers\Security;
use App\Services\MessageService;

api_method('GET', 'POST');
$user   = api_require_auth();
$uid    = (int) $user['id'];
$method = strtoupper($_SERVER['REQUEST_METHOD']);
$svc    = new MessageService();
$pdo    = Database::pdo();

if ($method === 'GET') {
    $convId = (int) ($_GET['conv'] ?? 0);

    if ($convId > 0) {
        // Konuşmada katılımcı mı?
        $chk = $pdo->prepare(
            'SELECT 1 FROM message_participants WHERE conversation_id = ? AND user_id = ? LIMIT 1'
        );
        $chk->execute([$convId, $uid]);
        if (!$chk->fetch()) {
            api_error('Bu konuşmaya erisim yetkiniz yok.', 403, 'FORBIDDEN');
        }

        // Mesajları çek
        $msgs = $pdo->prepare(
            'SELECT m.id, m.sender_id, u.username AS sender_username,
                    m.body, m.created_at, m.read_at
             FROM messages m
             JOIN users u ON u.id = m.sender_id
             WHERE m.conversation_id = ?
             ORDER BY m.created_at ASC'
        );
        $msgs->execute([$convId]);
        $rows = $msgs->fetchAll();

        // Okundu işaretle
        $pdo->prepare(
            'UPDATE messages SET read_at = ? WHERE conversation_id = ? AND sender_id != ? AND read_at IS NULL'
        )->execute([microtime(true), $convId, $uid]);

        api_ok([
            'conversation_id' => $convId,
            'messages'        => array_map(static fn(array $m): array => [
                'id'              => (int) $m['id'],
                'sender_id'       => (int) $m['sender_id'],
                'sender_username' => $m['sender_username'],
                'body'            => $m['body'],
                'created_at'      => $m['created_at'],
                'read_at'         => $m['read_at'],
                'is_mine'         => (int) $m['sender_id'] === $uid,
            ], $rows),
        ]);
    }

    // Konuşma listesi
    $convs = $pdo->prepare(
        'SELECT c.id, c.listing_id, c.updated_at,
                l.title AS listing_title,
                (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id AND sender_id != ? AND read_at IS NULL) AS unread
         FROM message_conversations c
         JOIN message_participants p ON p.conversation_id = c.id AND p.user_id = ?
         LEFT JOIN trade_listings l ON l.id = c.listing_id
         ORDER BY c.updated_at DESC'
    );
    $convs->execute([$uid, $uid]);
    $rows = $convs->fetchAll();

    api_ok([
        'conversations' => array_map(static fn(array $c): array => [
            'id'            => (int) $c['id'],
            'listing_id'    => $c['listing_id'] ? (int) $c['listing_id'] : null,
            'listing_title' => $c['listing_title'] ?? null,
            'unread'        => (int) $c['unread'],
            'updated_at'    => $c['updated_at'],
        ], $rows),
    ]);
}

// POST — mesaj gönder
Security::rateLimit('api_msg_send_' . $uid, 20, 60);

$body   = api_json_body();
$text   = trim((string) ($body['body'] ?? ''));
$convId = (int) ($body['conversation_id'] ?? 0);
$listId = (int) ($body['listing_id'] ?? 0);

if ($text === '') {
    api_error('Mesaj metni bos olamaz.', 422, 'EMPTY_BODY');
}
if (mb_strlen($text) > 2000) {
    api_error('Mesaj en fazla 2000 karakter olabilir.', 422, 'TOO_LONG');
}

if ($convId <= 0 && $listId <= 0) {
    api_error('conversation_id veya listing_id gerekli.', 422, 'MISSING_FIELDS');
}

try {
    if ($convId > 0) {
        $msgId = $svc->sendToConversation($convId, $uid, $text);
    } else {
        $msgId = $svc->sendToListing($listId, $uid, $text);
    }
} catch (Throwable $e) {
    api_error($e->getMessage(), 400, 'SEND_ERROR');
}

api_ok(['message_id' => $msgId], 201);
