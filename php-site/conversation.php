<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/MessageService.php';
require_once __DIR__ . '/app/Services/ListingService.php';

use App\Services\ListingService;
use App\Services\MessageService;

cx_bootstrap();

if (!cx_messages_enabled()) {
    cx_flash('error', 'Mesajlaşma şu an kapalı.');
    cx_redirect('/index.php');
}

$user = cx_require_user();
$userId = (int) $user['id'];
$msgSvc = new MessageService();
$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);

$convId = (int) ($_GET['id'] ?? 0);
$listingId = (int) ($_GET['listing_id'] ?? 0);
$sellerId = (int) ($_GET['seller_id'] ?? 0);

if ($convId <= 0 && $listingId > 0) {
    $listingSvc = new ListingService($base);
    $item = $listingSvc->findById($listingId, $userId);
    if ($item === null || !cx_can_view_listing($user, $item)) {
        cx_flash('error', 'İlan bulunamadı.');
        cx_redirect('/index.php');
    }
    if (!cx_listing_is_public((string) ($item['status'] ?? ''))) {
        cx_flash('error', 'Bu ilana mesaj gönderilemez.');
        cx_redirect('/listing.php?id=' . $listingId);
    }
    $ownerId = (int) ($item['owner_id'] ?? 0);
    if ($ownerId <= 0 || $ownerId === $userId) {
        cx_flash('error', 'Kendi ilanınıza mesaj gönderemezsiniz.');
        cx_redirect('/listing.php?id=' . $listingId);
    }
    try {
        $convId = $msgSvc->findOrCreateForListing($listingId, $userId, $ownerId);
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
        cx_redirect('/listing.php?id=' . $listingId);
    }
    cx_redirect('/conversation.php?id=' . $convId);
}

if ($convId <= 0 && $sellerId > 0) {
    if ($sellerId === $userId) {
        cx_flash('error', 'Kendinize mesaj gönderemezsiniz.');
        cx_redirect('/galeri.php?id=' . $sellerId);
    }
    try {
        $convId = $msgSvc->findOrCreateForSeller($sellerId, $userId);
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
        cx_redirect('/galeri.php?id=' . $sellerId);
    }
    cx_redirect('/conversation.php?id=' . $convId);
}

if ($convId <= 0) {
    cx_redirect('/messages.php');
}

$conv = $msgSvc->conversationForUser($convId, $userId);
if ($conv === null) {
    cx_flash('error', 'Sohbet bulunamadı.');
    cx_redirect('/messages.php');
}

$msgSvc->markRead($convId, $userId);
$messages = $msgSvc->messages($convId, $userId);

$otherName = trim((string) ($conv['other_username'] ?? 'Kullanıcı'));
$listingTitle = trim((string) ($conv['listing_title'] ?? ''));
$listingRefId = (int) ($conv['listing_ref_id'] ?? 0);
$threadTitle = $listingTitle !== '' ? $listingTitle : ('Galeri · ' . $otherName);

ob_start();
?>
<p><a class="link-gold" href="/messages.php">← Mesajlar</a></p>

<div class="msg-thread-head">
  <h1 class="section-title msg-thread-head__title"><?= cx_e($threadTitle) ?></h1>
  <p class="section-sub msg-thread-head__sub">
    <?= cx_e($otherName) ?> ile güvenli mesajlaşma — telefon numarası paylaşılmaz.
  </p>
  <?php if ($listingRefId > 0): ?>
  <a class="msg-thread-head__listing link-gold" href="/listing.php?id=<?= $listingRefId ?>">İlanı gör →</a>
  <?php endif; ?>
</div>

<div class="msg-thread" id="msg-thread">
  <?php if ($messages === []): ?>
  <p class="empty-state msg-thread__empty">Henüz mesaj yok. İlk mesajı siz yazın.</p>
  <?php else: ?>
    <?php foreach ($messages as $m): ?>
      <?php
        $mine = (int) ($m['sender_id'] ?? 0) === $userId;
        $time = (float) ($m['created_at'] ?? 0);
        $timeLabel = $time > 0 ? date('d.m.Y H:i', (int) $time) : '';
      ?>
      <div class="msg-bubble<?= $mine ? ' msg-bubble--mine' : ' msg-bubble--theirs' ?>">
        <?php if (!$mine): ?>
        <span class="msg-bubble__author"><?= cx_e((string) ($m['sender_username'] ?? '')) ?></span>
        <?php endif; ?>
        <p class="msg-bubble__body"><?= nl2br(cx_e((string) ($m['body'] ?? '')), false) ?></p>
        <?php if ($timeLabel !== ''): ?>
        <time class="msg-bubble__time" datetime="<?= cx_e(date('c', (int) $time)) ?>"><?= cx_e($timeLabel) ?></time>
        <?php endif; ?>
      </div>
    <?php endforeach; ?>
  <?php endif; ?>
</div>

<form class="msg-compose" method="post" action="/message-send.php">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="conversation_id" value="<?= $convId ?>">
  <input type="hidden" name="back" value="/conversation.php?id=<?= $convId ?>">
  <label class="visually-hidden" for="msg-body">Mesajınız</label>
  <textarea id="msg-body" name="body" rows="3" maxlength="2000" required placeholder="Mesajınızı yazın…"></textarea>
  <button class="btn-primary msg-compose__send" type="submit">Gönder</button>
</form>

<script>
(function () {
  var el = document.getElementById('msg-thread');
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
})();
</script>
<?php
$content = ob_get_clean();
$title = 'Sohbet';
$layout = 'app';
$navActive = 'messages';
require __DIR__ . '/views/layout.php';
