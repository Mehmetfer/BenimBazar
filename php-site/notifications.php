<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/NotificationService.php';

use App\Helpers\Security;
use App\Services\NotificationService;

cx_bootstrap();
$user = cx_require_user();
$svc = new NotificationService();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    if (isset($_POST['mark_all_read'])) {
        $svc->markAllRead((int) $user['id']);
        cx_flash('ok', 'Tum bildirimler okundu.');
    } elseif (isset($_POST['notification_id'])) {
        $svc->markRead((int) $_POST['notification_id'], (int) $user['id']);
    }
    cx_redirect('/notifications.php');
}

$items = $svc->listForUser((int) $user['id']);
$unread = $svc->unreadCount((int) $user['id']);

ob_start();
?>
<p><a class="link-gold" href="/index.php">← Ana sayfa</a></p>
<h1 class="section-title">Bildirimler</h1>
<?php if ($unread > 0): ?>
<form method="post" style="margin:.5rem 0 1rem">
  <?= cx_csrf_field() ?>
  <button class="btn-sm" type="submit" name="mark_all_read" value="1">Tumunu okundu isaretle</button>
</form>
<?php endif; ?>

<?php if ($items === []): ?>
  <p class="empty-state">Henuz bildirim yok.</p>
<?php else: ?>
  <div class="notify-list">
    <?php foreach ($items as $n): ?>
      <?php
        $isUnread = empty($n['read_at']);
        $type = (string) ($n['type'] ?? '');
        $isReject = $type === 'admin_rejected';
        $isApproved = $type === 'admin_approved';
        $isPriceDrop = $type === 'price_drop';
        $isFavWatch = in_array($type, ['price_rise', 'listing_removed', 'listing_sold', 'fav_photos', 'fav_seller_reply'], true);
        $entityId = (int) ($n['entity_id'] ?? 0);
        $entityType = (string) ($n['entity_type'] ?? '');
        $href = '/my-listings.php';
        if ($entityType === 'trade_listing' && $entityId > 0) {
            $href = '/listing.php?id=' . $entityId;
        } elseif ($entityType === 'conversation' && $entityId > 0) {
            $href = '/conversation.php?id=' . $entityId;
        }
        $linkLabel = $entityType === 'conversation' ? 'Sohbet' : 'İlan';
        $bodyRaw = rtrim((string) ($n['body'] ?? ''));
        if ($bodyRaw !== '' && !str_ends_with($bodyRaw, '🤲')) {
            $bodyRaw .= "\n\n🤲";
        }
        $bodyHtml = nl2br(cx_e($bodyRaw), false);
        $itemClass = 'notify-item';
        if ($isUnread) {
            $itemClass .= ' is-unread';
        }
        if ($isReject) {
            $itemClass .= ' notify-item--reject';
        } elseif ($isApproved) {
            $itemClass .= ' notify-item--approved';
        } elseif ($isPriceDrop || $type === 'price_rise') {
            $itemClass .= ' notify-item--price-drop';
        } elseif ($isFavWatch) {
            $itemClass .= ' notify-item--fav-watch';
        }
      ?>
      <article class="<?= $itemClass ?>">
        <div class="notify-item__title"><?= cx_e((string) ($n['title'] ?? '')) ?></div>
        <div class="notify-item__body"><?= $bodyHtml ?></div>
        <div class="notify-item__actions">
          <a class="btn-sm" href="<?= cx_e($href) ?>"><?= cx_e($linkLabel) ?></a>
          <?php if ($isUnread): ?>
          <form method="post" style="display:inline">
            <?= cx_csrf_field() ?>
            <input type="hidden" name="notification_id" value="<?= (int) ($n['id'] ?? 0) ?>">
            <button class="btn-sm" type="submit">Okundu</button>
          </form>
          <?php endif; ?>
        </div>
      </article>
    <?php endforeach; ?>
  </div>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Bildirimler';
$layout = 'app';
$navActive = 'notifications';
require __DIR__ . '/views/layout.php';
