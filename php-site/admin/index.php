<?php

declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';
require_once dirname(__DIR__) . '/app/Services/UserAdminService.php';
require_once dirname(__DIR__) . '/app/Services/AdminListingService.php';

use App\Helpers\Security;
use App\Services\AdminListingService;
use App\Services\UserAdminService;

cx_bootstrap();
$user = cx_require_staff();

try {
    $svc = new AdminListingService();
$q = trim((string) ($_GET['q'] ?? ''));
$statusFilter = trim((string) ($_GET['status'] ?? ''));
if (!in_array($statusFilter, ['', 'pending', 'approved', 'rejected', 'expired', 'sold'], true)) {
    $statusFilter = '';
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['sync_published']) && cx_is_admin($user)) {
    Security::requireCsrf();
    Security::rateLimit('admin_sync_published', 5, 300);
    try {
        $n = $svc->syncPublishedToActive($user);
        cx_flash('ok', 'Yayin durumu esitlendi: ' . $n . ' ilan ACTIVE (yayinda).');
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect('/admin/?' . http_build_query(array_filter(['q' => $q ?: null, 'status' => $statusFilter ?: null])));
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['decision'], $_POST['listing_id'])) {
    Security::requireCsrf();
    Security::rateLimit('admin_listing_decision', 80, 300);
    $lid = (int) $_POST['listing_id'];
    $dec = strtoupper((string) $_POST['decision']);
    $map = ['APPROVE' => 'APPROVED', 'REJECT' => 'REJECTED', 'DELETE' => 'CANCELLED'];

    try {
        if ($dec === 'REQUEST_EDIT') {
            $note = trim((string) ($_POST['edit_note'] ?? 'Lutfen ilaninizi guncelleyin.'));
            $svc->requestEdit($lid, $user, $note);
            cx_flash('ok', 'Ilan #' . cx_listing_no($lid) . ' icin duzenleme istendi.');
        } elseif ($dec === 'DELETE' && !cx_can_cancel_listings($user)) {
            cx_flash('error', 'İlan silme yalnızca yönetici / superadmin içindir.');
        } elseif (isset($map[$dec])) {
            $reason = trim((string) ($_POST['reject_reason'] ?? ''));
            $svc->setStatus($lid, $map[$dec], $user, $reason);
            cx_flash('ok', 'İlan #' . cx_listing_no($lid) . ' → ' . cx_listing_status_label($map[$dec]));
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    $redir = '/admin/?' . http_build_query(array_filter(['q' => $q ?: null, 'status' => $statusFilter ?: null]));
    cx_redirect($redir);
}

$stats = $svc->stats();
$rows = $svc->list($q !== '' ? $q : null, $statusFilter !== '' ? $statusFilter : null);
if ($statusFilter === 'pending') {
    $adminTab = 'pending';
} elseif ($statusFilter === 'expired') {
    $adminTab = 'expired';
} else {
    $adminTab = 'listings';
}

ob_start();
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<div class="admin-stats">
  <div class="admin-stat">
    <span class="admin-stat__num"><?= (int) $stats['total'] ?></span>
    <span class="admin-stat__label">Toplam ilan</span>
  </div>
  <div class="admin-stat admin-stat--pending">
    <span class="admin-stat__num"><?= (int) $stats['pending'] ?></span>
    <span class="admin-stat__label">Onay bekliyor</span>
  </div>
  <div class="admin-stat admin-stat--approved">
    <span class="admin-stat__num"><?= (int) $stats['published'] ?></span>
    <span class="admin-stat__label">Yayinda (site)</span>
  </div>
  <div class="admin-stat">
    <span class="admin-stat__num"><?= (int) $stats['approved_only'] ?> / <?= (int) $stats['active_only'] ?></span>
    <span class="admin-stat__label">APPROVED / ACTIVE</span>
  </div>
  <div class="admin-stat admin-stat--rejected">
    <span class="admin-stat__num"><?= (int) $stats['rejected'] ?></span>
    <span class="admin-stat__label">Reddedildi</span>
  </div>
  <?php if (($stats['cancelled'] ?? 0) > 0): ?>
  <div class="admin-stat">
    <span class="admin-stat__num"><?= (int) $stats['cancelled'] ?></span>
    <span class="admin-stat__label">Silindi</span>
  </div>
  <?php endif; ?>
</div>

<?php if (cx_is_admin($user) && ((int) ($stats['approved_only'] ?? 0) > 0 || (int) ($stats['published'] ?? 0) > 0)): ?>
<form class="admin-toolbar" method="post" style="margin-bottom:1rem">
  <?= cx_csrf_field() ?>
  <input type="hidden" name="sync_published" value="1">
  <button class="admin-toolbar__btn admin-toolbar__btn--primary" type="submit"
    onclick="return confirm('Tum yayindaki ilanlar ACTIVE yapilsin mi? (APPROVED + ACTIVE)')">
    Yayin durumunu esitle (ACTIVE)
  </button>
  <span class="muted" style="margin-left:.75rem">Ana sayfa en fazla <?= (int) ($stats['site_feed_limit'] ?? 500) ?> ilan gosterir.</span>
</form>
<?php endif; ?>

<form class="admin-toolbar" method="get">
  <?php if ($statusFilter !== ''): ?>
    <input type="hidden" name="status" value="<?= cx_e($statusFilter) ?>">
  <?php endif; ?>
  <input class="admin-toolbar__search" type="search" name="q" value="<?= cx_e($q) ?>" placeholder="İlan no, başlık, kategori veya kullanıcı…">
  <button class="admin-toolbar__btn" type="submit">Ara</button>
  <?php if ($q !== '' || $statusFilter !== ''): ?>
    <a class="admin-toolbar__clear" href="/admin/">Temizle</a>
  <?php endif; ?>
</form>

<p class="admin-list-meta">
  <?= count($rows) ?> kayıt · Rol: <strong><?= cx_e(UserAdminService::label((string) ($user['role'] ?? ''))) ?></strong>
  <?php if ($statusFilter === 'pending' && (int) ($stats['pending'] ?? 0) > count($rows)): ?>
    <span class="admin-list-meta__hint"> · Sayaçtaki <?= (int) $stats['pending'] ?> bekleyen ilanın tamamı listeleniyor.</span>
  <?php endif; ?>
</p>

<?php if ($rows === []): ?>
  <div class="admin-empty">Bu filtreye uygun ilan bulunamadı.</div>
<?php else: ?>
  <div class="admin-list">
    <?php foreach ($rows as $r):
      $no = (int) ($r['listing_no'] ?? cx_listing_no((int) $r['id']));
      $thumb = $r['photo_thumb'] ?? null;
      $appCfg = cx_app_config();
      $siteUrl = (string) ($appCfg['url'] ?? '');
      $uploadsUrl = (string) ($appCfg['uploads_url'] ?? '/uploads');
      $mode = strtoupper((string) ($r['listing_mode'] ?? 'TRADE'));
      $price = isset($r['price_tl']) ? (float) $r['price_tl'] : null;
    ?>
    <article class="admin-row">
      <a class="admin-row__thumb" href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>">
        <?php if ($thumb): ?>
          <?= cx_photo_img((string) $thumb, 'thumb', ['class' => '', 'alt' => '', 'watermark' => false], $siteUrl, $uploadsUrl) ?>
        <?php else: ?>
          <span class="admin-row__no-photo">Foto yok</span>
        <?php endif; ?>
      </a>
      <div class="admin-row__body">
        <div class="admin-row__top">
          <span class="admin-row__no">#<?= $no ?></span>
          <span class="admin-badge admin-badge--<?= cx_e(cx_listing_status_class((string) $r['status'])) ?>">
            <?= cx_e(cx_listing_status_label((string) $r['status'])) ?>
          </span>
          <?php
            $rowHasSimilar = false;
            if ($statusFilter === 'pending') {
                $rowAttrs = cx_listing_attrs($r);
                if ($rowAttrs !== []) {
                    $rowHasSimilar = cx_listing_has_similar($rowAttrs, (int) $r['id']);
                }
            }
          ?>
          <?php if ($rowHasSimilar): ?>
            <a class="admin-badge admin-badge--similar" href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>">Benzer?</a>
          <?php endif; ?>
          <?php if ($mode === 'SALE' && $price !== null && $price > 0): ?>
            <span class="admin-row__price"><?= cx_e(number_format($price, 0, ',', '.')) ?> TL</span>
          <?php else: ?>
            <span class="admin-row__price admin-row__price--trade">Takas</span>
          <?php endif; ?>
        </div>
        <h2 class="admin-row__title">
          <a href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>"><?= cx_e($r['title']) ?></a>
        </h2>
        <p class="admin-row__meta">
          <?= cx_e($r['subcategory'] ?: $r['category']) ?> · <?= cx_e($r['location'] ?: '—') ?> · @<?= cx_e($r['owner_username']) ?>
          · 👁 <?= (int) ($r['view_count'] ?? 0) ?>
          · ❤️ <?= (int) ($r['favorite_count'] ?? 0) ?>
          · 💬 <?= (int) ($r['message_count'] ?? 0) ?>
          · 📅 <?= (int) ($r['days_live'] ?? 0) ?> gün
        </p>
      </div>
      <div class="admin-row__actions">
        <a class="admin-btn admin-btn--primary" href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>">Düzenle</a>
        <form method="post" class="admin-row__quick">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="listing_id" value="<?= (int) $r['id'] ?>">
          <?php if (!in_array(strtoupper((string) $r['status']), ['APPROVED', 'ACTIVE'], true)): ?>
            <button class="admin-btn admin-btn--ok" name="decision" value="APPROVE" type="submit">Onayla</button>
          <?php endif; ?>
          <?php if ($statusFilter === 'expired'): ?>
            <button class="admin-btn admin-btn--warn" name="decision" value="REQUEST_EDIT" type="submit">Duzenleme iste</button>
          <?php endif; ?>
          <?php if (strtoupper((string) $r['status']) !== 'REJECTED'): ?>
            <button class="admin-btn admin-btn--warn" name="decision" value="REJECT" type="submit"
                    onclick="return window.cxAdminRejectReason(this.form)">Reddet</button>
          <?php endif; ?>
          <?php if (cx_can_cancel_listings($user)): ?>
            <button class="admin-btn admin-btn--danger" name="decision" value="DELETE" type="submit" onclick="return confirm('İlan silinsin mi?')">Sil</button>
          <?php endif; ?>
        </form>
        <a class="admin-btn" href="/listing.php?id=<?= (int) $r['id'] ?>" target="_blank" rel="noopener">Önizle</a>
        <a class="admin-btn admin-btn--gold" href="/share-card.php?id=<?= (int) $r['id'] ?>" target="_blank" rel="noopener">IG kart</a>
      </div>
    </article>
    <?php endforeach; ?>
  </div>
<?php endif; ?>

<?php require dirname(__DIR__) . '/views/partials/admin-reject-reason.php'; ?>

<?php
$content = ob_get_clean();
$title = 'Yönetim — İlanlar';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
} catch (Throwable $e) {
    \App\Helpers\ErrorHandler::handleException($e);
}
