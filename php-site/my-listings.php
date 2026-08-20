<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/ListingWriteService.php';
require_once __DIR__ . '/app/Services/SocialService.php';
require_once __DIR__ . '/app/Services/SellerPublicService.php';

use App\Helpers\Security;
use App\Services\ListingWriteService;
use App\Services\SellerPublicService;

cx_bootstrap();
$user = cx_require_user();
if (cx_is_corporate($user)) {
    cx_redirect('/gallery-panel.php');
}
$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$writer = new ListingWriteService();
$sellerSvc = new SellerPublicService($base);

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    Security::requireCsrf();
    if (isset($_POST['cancel_id'])) {
        $lid = (int) $_POST['cancel_id'];
        if ($writer->cancel($lid, (int) $user['id'], false)) {
            cx_flash('ok', 'Ilan iptal edildi.');
        } else {
            cx_flash('error', 'Ilan iptal edilemedi.');
        }
    } elseif (cx_is_dealer($user) && !empty($_FILES['gallery_logo']['name'])) {
        $saved = cx_save_uploaded_gallery_logo($_FILES['gallery_logo'], (int) $user['id']);
        if ($saved && $sellerSvc->updateAvatar((int) $user['id'], $saved)) {
            cx_flash('ok', 'Galeri logosu güncellendi.');
        } else {
            cx_flash('error', 'Logo yüklenemedi. JPG/PNG/WEBP deneyin.');
        }
    }
    cx_redirect('/my-listings.php');
}

$rows = $writer->mine((int) $user['id']);
$siteUrl = (string) ($app['url'] ?? '');
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
$quota = cx_user_listing_quota($user);
$isDealer = cx_is_dealer($user);
$publicGalleryUrl = $isDealer ? '/galeri.php?id=' . (int) $user['id'] : '';
$logoSrc = '';
if ($isDealer) {
    $ownerProfile = $sellerSvc->findOwner((int) $user['id']);
    $logoSrc = cx_user_avatar_src((string) (($ownerProfile['avatar_url'] ?? '') ?: ''), $uploadsUrl);
}

ob_start();
?>
<h1 class="section-title">Ilanlarim</h1>
<p class="section-sub">Durum, goruntulenme ve islemler.</p>
<?php if (!cx_user_phone_verified($user)): ?>
<div class="verify-banner">
  <div class="verify-banner__text">
    <strong>Telefonunuzu doğrulayın</strong> — güvenilir satıcı rozeti kazanın.
  </div>
  <a class="btn-sm verify-banner__btn" href="/verify-phone.php">Doğrula</a>
</div>
<?php endif; ?>
<?php if ($isDealer): ?>
<p class="admin-list-meta" style="margin-bottom:10px">
  <a class="link-gold" href="<?= cx_e($publicGalleryUrl) ?>">Herkese açık galeri sayfanız →</a>
</p>
<form class="vip-panel__logo-form" method="post" enctype="multipart/form-data" style="margin-bottom:14px">
  <?= cx_csrf_field() ?>
  <div class="vip-panel__logo-preview<?= $logoSrc === '' ? ' vip-panel__logo-preview--empty' : '' ?>">
    <?php if ($logoSrc !== ''): ?>
      <img src="<?= cx_e($logoSrc) ?>" alt="Galeri logosu">
    <?php else: ?>
      <span>Logo yok</span>
    <?php endif; ?>
  </div>
  <div class="vip-panel__logo-fields">
    <label class="vip-panel__logo-label">Galeri logosu</label>
    <input type="file" name="gallery_logo" accept="image/jpeg,image/png,image/webp" required>
    <button class="btn-sm btn-sm--gold" type="submit">Logoyu kaydet</button>
  </div>
</form>
<?php endif; ?>
<p class="admin-list-meta" style="margin-bottom:12px"><?= cx_e($quota['message']) ?>
  <?php if (!empty($quota['contact_admin'])): ?>
    — <a class="link-gold" href="<?= cx_e(cx_admin_contact_href()) ?>">Admin ile iletisime gec</a>
  <?php endif; ?>
</p>
<?php if ($quota['ok']): ?>
<p><a class="link-gold" href="/create-listing.php">+ Yeni ilan olustur</a> (kalan: <?= (int) $quota['remaining'] ?>)</p>
<?php else: ?>
<p><span class="muted">Yeni ilan kotaniz dolu.</span>
  <?php if (!empty($quota['contact_admin'])): ?>
  <a class="link-gold" href="<?= cx_e(cx_admin_contact_href()) ?>">Admin ile iletisime gec</a>
  <?php endif; ?>
</p>
<?php endif; ?>

<?php if ($rows === []): ?>
<p class="empty-state">Henuz ilaniniz yok.</p>
<?php else: ?>
<div class="mine-list">
<?php foreach ($rows as $item):
    $no = cx_listing_no((int) $item['id'], $base);
    $st = strtoupper((string) ($item['status'] ?? ''));
    $photos = cx_photo_urls($item['photo_urls'] ?? '[]', $uploadsUrl);
    $thumb = $photos[0] ?? '';
    $expired = !empty($item['is_expired']);
?>
  <article class="mine-row<?= cx_listing_is_sold($st) ? ' mine-row--sold' : '' ?>">
    <div class="mine-row__media">
      <?php if ($thumb): ?>
        <?= cx_photo_img($thumb, 'thumb', ['class' => 'mine-row__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?>
      <?php else: ?>
        <div class="mine-row__img mine-row__img--empty">Foto yok</div>
      <?php endif; ?>
      <?php if (cx_listing_is_sold($st)): ?><span class="mine-row__ribbon">SATILDI</span><?php endif; ?>
    </div>
    <div class="mine-row__body">
      <div class="mine-row__status"><?= cx_listing_status_emoji($st) ?> <?= cx_e(cx_listing_status_label($st)) ?></div>
      <h3 class="mine-row__title"><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_e($item['title']) ?></a></h3>
      <div class="mine-row__meta">#<?= $no ?> · 👁 <?= (int) ($item['view_count'] ?? 0) ?> · ❤️ <?= (int) ($item['favorite_count'] ?? 0) ?> · 📅 <?= (int) ($item['days_live'] ?? 0) ?> gün</div>
      <?php if (!cx_listing_can_adjust_price($item)): ?>
      <div class="mine-row__price"><?= cx_e(cx_listing_price_line($item)) ?></div>
      <?php endif; ?>
      <?php
        $back = '/my-listings.php';
        require __DIR__ . '/views/partials/price-adjust.php';
      ?>
      <?php if ($expired): ?>
        <div class="mine-row__alert">⚠️ Bu ilanın süresi doldu.</div>
      <?php endif; ?>
    </div>
    <div class="mine-row__actions">
      <a class="btn-sm" href="/listing.php?id=<?= (int) $item['id'] ?>">Detay</a>
      <?php if (!in_array($st, ['CANCELLED', 'SOLD'], true)): ?>
      <a class="btn-sm" href="/edit-listing.php?id=<?= (int) $item['id'] ?>">Duzenle</a>
      <?php endif; ?>
      <?php if (in_array($st, ['APPROVED', 'ACTIVE'], true)): ?>
      <form method="post" action="/listing-action.php" style="display:inline" onsubmit="return confirm('Bu ilan satildi olarak isaretlenecek. Devam etmek istiyor musunuz?')">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="action" value="mark_sold">
        <input type="hidden" name="listing_id" value="<?= (int) $item['id'] ?>">
        <input type="hidden" name="back" value="/my-listings.php">
        <button class="btn-sm" type="submit">Satildi yap</button>
      </form>
      <?php endif; ?>
      <?php if ($expired): ?>
      <form method="post" action="/listing-action.php" style="display:inline">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="action" value="republish">
        <input type="hidden" name="listing_id" value="<?= (int) $item['id'] ?>">
        <input type="hidden" name="back" value="/my-listings.php">
        <button class="btn-sm btn-sm--gold" type="submit">Yeniden yayinla</button>
      </form>
      <?php endif; ?>
      <?php if ($st !== 'CANCELLED'): ?>
      <form method="post" style="display:inline">
        <?= cx_csrf_field() ?>
        <input type="hidden" name="cancel_id" value="<?= (int) $item['id'] ?>">
        <button class="btn-sm" type="submit" onclick="return confirm('Ilan iptal edilsin mi?')">Iptal</button>
      </form>
      <?php endif; ?>
    </div>
  </article>
<?php endforeach; ?>
</div>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Ilanlarim';
$layout = 'app';
$navActive = 'mine';
require __DIR__ . '/views/layout.php';
