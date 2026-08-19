<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/MessageService.php';

use App\Helpers\Security;
use App\Services\MessageService;

cx_bootstrap();

if (!cx_messages_enabled()) {
    cx_flash('error', 'Mesajlaşma şu an kapalı.');
    cx_redirect('/index.php');
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    cx_flash('error', 'Geçersiz istek.');
    cx_redirect('/messages.php');
}

Security::requireCsrf();
$user = cx_require_user();

$convId = (int) ($_POST['conversation_id'] ?? 0);
$body = (string) ($_POST['body'] ?? '');
$back = (string) ($_POST['back'] ?? '/messages.php');

if ($convId <= 0) {
    cx_redirect('/messages.php');
}

try {
    (new MessageService())->send($convId, (int) $user['id'], $body);
    cx_flash('ok', 'Mesaj gönderildi.');
} catch (Throwable $e) {
    cx_flash('error', $e->getMessage());
}

cx_redirect(cx_safe_next($back !== '' ? $back : '/conversation.php?id=' . $convId));
