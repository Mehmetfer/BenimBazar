<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

use App\Helpers\Database;

cx_bootstrap();
$user = cx_require_user();
$pdo = Database::pdo();

$stmt = $pdo->prepare(
    'SELECT c.id, c.updated_at, l.title AS listing_title,
            (SELECT body FROM messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS last_body
     FROM message_conversations c
     JOIN message_participants p ON p.conversation_id = c.id
     LEFT JOIN trade_listings l ON l.id = c.listing_id
     WHERE p.user_id = ?
     ORDER BY c.updated_at DESC LIMIT 50'
);
try {
    $stmt->execute([(int) $user['id']]);
    $inbox = $stmt->fetchAll();
} catch (Throwable $e) {
    $inbox = [];
}

ob_start();
?>
<h1 class="section-title">Mesajlar</h1>
<p class="section-sub">Guvenli mesajlasma — telefon numarasi paylasilmaz.</p>

<?php if ($inbox === []): ?>
<div class="empty-state">
  Henuz mesajiniz yok.<br>
  Bir ilan detayindan mesaj baslatabilirsiniz (yakinda).
</div>
<p style="text-align:center;margin-top:16px"><a class="link-gold" href="/index.php">Ilanlara don</a></p>
<?php else: ?>
<ul class="msg-list">
<?php foreach ($inbox as $row): ?>
  <li class="msg-item">
    <strong><?= cx_e($row['listing_title'] ?? 'Sohbet') ?></strong>
    <span><?= cx_e(mb_substr((string) ($row['last_body'] ?? ''), 0, 80)) ?></span>
  </li>
<?php endforeach; ?>
</ul>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Mesajlar';
$layout = 'app';
$navActive = 'messages';
require __DIR__ . '/views/layout.php';
