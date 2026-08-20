<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SellerPublicService.php';

use App\Services\SellerPublicService;

cx_bootstrap();

$app = cx_app_config();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$ownerId = (int) ($_GET['id'] ?? 0);
$user = cx_current_user();
$svc = new SellerPublicService($base);
$owner = $svc->findOwner($ownerId);

if ($owner === null) {
    cx_flash('error', 'Satıcı bulunamadı.');
    cx_redirect('/index.php');
}

if (!empty($owner['is_corporate'])) {
    cx_redirect('/galeri.php?id=' . $ownerId);
}

$items = $svc->publicListings($ownerId, $user ? (int) $user['id'] : null, true);
$activeCount = 0;
foreach ($items as $row) {
    $st = strtoupper((string) ($row['status'] ?? ''));
    if (in_array($st, ['APPROVED', 'ACTIVE'], true)) {
        $activeCount++;
    }
}

$displayName = (string) ($owner['display_name'] ?? $owner['username'] ?? 'Üye');
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
$avatarSrc = cx_user_avatar_src((string) ($owner['avatar_url'] ?? ''), $uploadsUrl);
$favBack = '/satici.php?id=' . $ownerId;
$vehicleBrowse = true;

ob_start();
?>
<section class="seller-public">
  <p class="seller-public__back"><a class="link-gold" href="/index.php">← Ana sayfa</a></p>
  <header class="seller-public__head">
    <div class="seller-public__avatar<?= $avatarSrc === '' ? ' seller-public__avatar--mono' : '' ?>" aria-hidden="true">
      <?php if ($avatarSrc !== ''): ?>
        <img src="<?= cx_e($avatarSrc) ?>" alt="">
      <?php else: ?>
        <span><?= cx_e(mb_strtoupper(mb_substr($displayName, 0, 1))) ?></span>
      <?php endif; ?>
    </div>
    <div>
      <p class="seller-public__eyebrow">Üye ilanları</p>
      <h1 class="section-title"><?= cx_e($displayName) ?></h1>
      <p class="section-sub">@<?= cx_e((string) ($owner['username'] ?? '')) ?> · <?= (int) $activeCount ?> yayında · <?= count($items) ?> toplam</p>
    </div>
  </header>
  <?php
  require __DIR__ . '/views/partials/market-listings-grid.php';
  ?>
</section>
<?php
$content = ob_get_clean();
$title = $displayName . ' — İlanlar';
$layout = 'app';
$navActive = 'home';
require __DIR__ . '/views/layout.php';
