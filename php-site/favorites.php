<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SocialService.php';
require_once __DIR__ . '/app/Services/ListingService.php';

use App\Services\ListingService;
use App\Services\SocialService;

cx_bootstrap();
$app = cx_app_config();
$user = cx_require_user();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$raw = SocialService::myFavorites((int) $user['id']);
$svc = new ListingService($base);
$listings = [];
foreach ($raw as $row) {
    if (!cx_listing_is_public((string) ($row['status'] ?? ''))) {
        continue;
    }
    $found = $svc->findById((int) $row['id'], (int) $user['id']);
    if ($found !== null) {
        $listings[] = $found;
    }
}

ob_start();
?>
<p><a class="link-gold" href="/index.php">← Ana sayfa</a></p>
<h2 class="section-title">Favorilerim</h2>
<?php if ($listings === []): ?>
  <p class="empty-state">Henüz favori ilan yok.<br>Ana sayfada ♥ ile ekleyin.</p>
<?php else: ?>
<div class="feed-list">
<?php foreach ($listings as $item): ?>
  <?php
    $appCfg = cx_app_config();
    $siteUrl = (string) ($appCfg['url'] ?? '');
    $uploadsUrl = (string) ($appCfg['uploads_url'] ?? '/uploads');
    $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]', $uploadsUrl);
    $thumb = $photos[0] ?? '';
    $no = (int) ($item['listing_no'] ?? cx_listing_no((int) $item['id'], $base));
  ?>
  <article class="feed-card">
    <?php if ($thumb): ?><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_photo_img($thumb, 'card', ['class' => 'feed-card__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?></a><?php endif; ?>
    <div class="feed-card__body">
      <h3 class="feed-card__title"><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_e($item['title']) ?></a></h3>
      <div class="feed-card__ilan">İlan No: <?= $no ?></div>
      <div class="feed-card__actions">
        <a class="btn-sm" href="/share.php?id=<?= (int) $item['id'] ?>">Paylaş</a>
        <?= cx_favorite_toggle_form((int) $item['id'], '/favorites.php', true, 'btn-sm btn-fav active') ?>
      </div>
    </div>
  </article>
<?php endforeach; ?>
</div>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Favorilerim';
$layout = 'app';
$navActive = 'home';
require __DIR__ . '/views/layout.php';
