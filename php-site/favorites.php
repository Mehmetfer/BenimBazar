<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require_once __DIR__ . '/app/Services/SocialService.php';
require_once __DIR__ . '/app/Services/ListingService.php';
require_once __DIR__ . '/app/Services/PriceDropAlertService.php';

use App\Services\ListingService;
use App\Services\PriceDropAlertService;
use App\Services\SocialService;

cx_bootstrap();
$app = cx_app_config();
$user = cx_require_user();
$base = (int) ($app['listing_no_base'] ?? 1000000000);
$raw = SocialService::myFavorites((int) $user['id']);
$svc = new ListingService($base);
$alertSvc = new PriceDropAlertService();
$listings = [];
$inactive = [];
foreach ($raw as $row) {
    $status = (string) ($row['status'] ?? '');
    if (!cx_listing_is_public($status)) {
        $inactive[] = $row;
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
<p class="fav-watch-lead">
  Favori yalnızca yer imi değil. İlanı ♥ ile kaydettiğinizde fiyat düşüşü/yükselişi,
  yeni fotoğraf, ilanın kalkması ve satıcının cevabı için bildirim alırsınız.
  🔔 ile akıllı bildirimleri kapatabilirsiniz.
</p>
<?php if ($listings === [] && $inactive === []): ?>
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
    $watching = $alertSvc->isAlertEnabled((int) $user['id'], (int) $item['id']);
  ?>
  <article class="feed-card">
    <?php if ($thumb): ?><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_photo_img($thumb, 'card', ['class' => 'feed-card__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?></a><?php endif; ?>
    <div class="feed-card__body">
      <h3 class="feed-card__title"><a href="/listing.php?id=<?= (int) $item['id'] ?>"><?= cx_e($item['title']) ?></a></h3>
      <div class="feed-card__ilan">İlan No: <?= $no ?></div>
      <?php if (cx_price_drop_alerts_enabled()): ?>
        <div class="fav-watch-status<?= $watching ? ' is-on' : '' ?>">
          <?= $watching ? 'Akıllı bildirimler açık' : 'Akıllı bildirimler kapalı' ?>
        </div>
      <?php endif; ?>
      <div class="feed-card__actions">
        <a class="btn-sm" href="/share.php?id=<?= (int) $item['id'] ?>">Paylaş</a>
        <?= cx_favorite_toggle_form((int) $item['id'], '/favorites.php', true, 'btn-sm btn-fav active') ?>
        <?php if (cx_price_drop_alerts_enabled()): ?>
          <?= cx_price_alert_toggle_form((int) $item['id'], '/favorites.php', $watching, true) ?>
        <?php endif; ?>
      </div>
    </div>
  </article>
<?php endforeach; ?>
</div>
<?php if ($inactive !== []): ?>
  <h3 class="section-title" style="margin-top:1.5rem">Yayında olmayan favoriler</h3>
  <p class="muted" style="font-size:13px">Satıldı veya kaldırıldı. Bildirim geçmişinizde kaydı durur.</p>
  <ul class="fav-inactive">
    <?php foreach ($inactive as $row): ?>
      <li>
        <?= cx_e((string) ($row['title'] ?? 'İlan')) ?>
        · <?= cx_e(cx_listing_status_label((string) ($row['status'] ?? ''))) ?>
        <?= cx_favorite_toggle_form((int) $row['id'], '/favorites.php', true, 'btn-sm btn-fav active') ?>
      </li>
    <?php endforeach; ?>
  </ul>
<?php endif; ?>
<?php endif; ?>
<?php
$content = ob_get_clean();
$title = 'Favorilerim';
$layout = 'app';
$navActive = 'home';
require __DIR__ . '/views/layout.php';
