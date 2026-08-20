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

$ownerId = (int) ($_GET['id'] ?? 0);
$statusFilter = trim((string) ($_GET['status'] ?? ''));
if (!in_array($statusFilter, ['', 'pending', 'approved', 'rejected', 'sold', 'cancelled'], true)) {
    $statusFilter = '';
}

$owner = UserAdminService::findUser($ownerId);
if ($owner === null) {
    cx_flash('error', 'Kullanıcı bulunamadı.');
    cx_redirect('/admin/users.php');
}

$backQuery = http_build_query(array_filter([
    'id' => $ownerId,
    'status' => $statusFilter !== '' ? $statusFilter : null,
]));
$back = '/admin/user-listings.php?' . $backQuery;

$svc = new AdminListingService();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['decision'], $_POST['listing_id'])) {
    Security::requireCsrf();
    Security::rateLimit('admin_user_listing_decision', 80, 300);
    $lid = (int) $_POST['listing_id'];
    $dec = strtoupper((string) $_POST['decision']);
    $map = [
        'APPROVE' => 'APPROVED',
        'REJECT' => 'REJECTED',
        'HOLD' => 'PENDING_MODERATION',
        'DELETE' => 'CANCELLED',
    ];

    try {
        // Sadece bu kullaniciya ait ilanlar
        $item = $svc->find($lid);
        if ($item === null || (int) ($item['owner_id'] ?? 0) !== $ownerId) {
            throw new RuntimeException('İlan bu kullanıcıya ait değil.');
        }

        if ($dec === 'DELETE' && !cx_can_cancel_listings($user)) {
            cx_flash('error', 'İlan silme yalnızca yönetici / superadmin içindir.');
        } elseif (isset($map[$dec])) {
            $reason = trim((string) ($_POST['reject_reason'] ?? ''));
            $svc->setStatus($lid, $map[$dec], $user, $reason);
            cx_flash('ok', 'İlan #' . cx_listing_no($lid) . ' → ' . cx_listing_status_label($map[$dec]));
        } else {
            cx_flash('error', 'Geçersiz işlem.');
        }
    } catch (Throwable $e) {
        cx_flash('error', $e->getMessage());
    }
    cx_redirect($back);
}

$rows = $svc->listByOwner($ownerId, $statusFilter !== '' ? $statusFilter : null);
$labels = UserAdminService::roleLabels();
$role = (string) ($owner['role'] ?? 'user');

ob_start();
$adminTab = 'users';
?>
<?php require dirname(__DIR__) . '/views/partials/admin-shell.php'; ?>

<p class="admin-list-meta">
  <a class="link-gold" href="/admin/users.php">← Kullanıcılar</a>
</p>

<header class="admin-user-listings__head">
  <div>
    <h1 class="section-title">@<?= cx_e((string) $owner['username']) ?> — ilanları</h1>
    <p class="section-sub">
      <?= cx_e($labels[$role] ?? $role) ?>
      · Toplam <?= (int) ($owner['listing_total'] ?? 0) ?>
      · Yayında <?= (int) ($owner['listing_published'] ?? 0) ?>
      · Bekleyen <?= (int) ($owner['listing_pending'] ?? 0) ?>
      <?php if (!empty($owner['email'])): ?> · <?= cx_e((string) $owner['email']) ?><?php endif; ?>
    </p>
  </div>
  <?php if (cx_owner_role_is_corporate($role)): ?>
  <a class="admin-btn" href="/galeri.php?id=<?= $ownerId ?>" target="_blank" rel="noopener">Galerisini aç</a>
  <?php else: ?>
  <a class="admin-btn" href="/satici.php?id=<?= $ownerId ?>" target="_blank" rel="noopener">Satıcı sayfası</a>
  <?php endif; ?>
</header>

<nav class="vip-panel__filters" aria-label="Durum filtresi" style="margin-bottom:14px">
  <a class="vip-panel__filter<?= $statusFilter === '' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>">Tümü</a>
  <a class="vip-panel__filter<?= $statusFilter === 'approved' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>&amp;status=approved">Yayında</a>
  <a class="vip-panel__filter<?= $statusFilter === 'pending' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>&amp;status=pending">Bekleyen</a>
  <a class="vip-panel__filter<?= $statusFilter === 'rejected' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>&amp;status=rejected">Reddedilen</a>
  <a class="vip-panel__filter<?= $statusFilter === 'sold' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>&amp;status=sold">Satıldı</a>
  <?php if (cx_can_cancel_listings($user)): ?>
  <a class="vip-panel__filter<?= $statusFilter === 'cancelled' ? ' is-active' : '' ?>" href="/admin/user-listings.php?id=<?= $ownerId ?>&amp;status=cancelled">Silinen</a>
  <?php endif; ?>
</nav>

<p class="admin-list-meta"><?= count($rows) ?> kayıt listeleniyor</p>

<?php if ($rows === []): ?>
  <div class="admin-empty">Bu filtrede ilan yok.</div>
<?php else: ?>
  <div class="admin-list">
    <?php foreach ($rows as $r):
      $no = (int) ($r['listing_no'] ?? cx_listing_no((int) $r['id']));
      $thumb = $r['photo_thumb'] ?? null;
      $appCfg = cx_app_config();
      $siteUrl = (string) ($appCfg['url'] ?? '');
      $uploadsUrl = (string) ($appCfg['uploads_url'] ?? '/uploads');
      $st = strtoupper((string) ($r['status'] ?? ''));
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
          <span class="admin-badge admin-badge--<?= cx_e(cx_listing_status_class($st)) ?>">
            <?= cx_e(cx_listing_status_label($st)) ?>
          </span>
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
          <?= cx_e(($r['subcategory'] ?: $r['category']) ?: '—') ?> · <?= cx_e($r['location'] ?: '—') ?>
          · 👁 <?= (int) ($r['view_count'] ?? 0) ?>
          · ❤️ <?= (int) ($r['favorite_count'] ?? 0) ?>
        </p>
      </div>
      <div class="admin-row__actions">
        <a class="admin-btn admin-btn--primary" href="/admin/listing-edit.php?id=<?= (int) $r['id'] ?>">Düzenle</a>
        <form method="post" class="admin-row__quick">
          <?= cx_csrf_field() ?>
          <input type="hidden" name="listing_id" value="<?= (int) $r['id'] ?>">
          <?php if (!in_array($st, ['APPROVED', 'ACTIVE'], true)): ?>
            <button class="admin-btn admin-btn--ok" name="decision" value="APPROVE" type="submit">Onayla</button>
          <?php endif; ?>
          <?php if (!in_array($st, ['PENDING_MODERATION', 'PENDING'], true)): ?>
            <button class="admin-btn admin-btn--warn" name="decision" value="HOLD" type="submit">Beklet</button>
          <?php endif; ?>
          <?php if ($st !== 'REJECTED'): ?>
            <button class="admin-btn admin-btn--warn" name="decision" value="REJECT" type="submit"
                    onclick="return window.cxAdminRejectReason(this.form)">Reddet</button>
          <?php endif; ?>
          <?php if (cx_can_cancel_listings($user) && $st !== 'CANCELLED'): ?>
            <button class="admin-btn admin-btn--danger" name="decision" value="DELETE" type="submit" onclick="return confirm('İlan silinsin mi?')">Sil</button>
          <?php endif; ?>
        </form>
        <a class="admin-btn" href="/listing.php?id=<?= (int) $r['id'] ?>" target="_blank" rel="noopener">Önizle</a>
      </div>
    </article>
    <?php endforeach; ?>
  </div>
<?php endif; ?>

<?php require dirname(__DIR__) . '/views/partials/admin-reject-reason.php'; ?>

<?php
$content = ob_get_clean();
$title = '@' . (string) $owner['username'] . ' — İlanlar';
$layout = 'admin';
$bodyClass = 'page-admin';
require dirname(__DIR__) . '/views/layout.php';
