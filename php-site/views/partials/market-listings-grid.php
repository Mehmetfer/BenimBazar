<?php

declare(strict_types=1);

/** @var list<array<string,mixed>> $items */
/** @var array<string,mixed>|null $user */
/** @var array<string,mixed> $app */
/** @var bool $vehicleBrowse */

$items = $items ?? [];
$user = $user ?? null;
$app = $app ?? cx_app_config();
$vehicleBrowse = $vehicleBrowse ?? true;
$siteUrl = (string) ($app['url'] ?? '');
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');
$favBack = (string) ($favBack ?? ($_SERVER['REQUEST_URI'] ?? '/index.php'));

if ($items === []):
?>
<p class="empty-state">Yayında ilan yok.</p>
<?php
    return;
endif;
?>
<div class="home-market__grid seller-public__grid">
<?php foreach ($items as $item):
    $photos = cx_photo_urls($item['photo_list'] ?? $item['photo_urls'] ?? '[]', $uploadsUrl);
    $thumb = $photos[0] ?? '';
    $vehicleLine = $vehicleBrowse ? cx_listing_vehicle_summary_line($item) : '';
    $featured = (int) ($item['favorite_count'] ?? 0) >= 2;
    $isSold = !empty($item['is_sold']) || cx_listing_is_sold((string) ($item['status'] ?? ''));
    $mode = strtoupper((string) ($item['listing_mode'] ?? 'TRADE'));
    $lid = (int) ($item['id'] ?? 0);
    $favFormCard = $user
        ? cx_favorite_toggle_form($lid, $favBack, !empty($item['is_favorited']), 'market-card__fav-link')
        : '';
?>
  <article class="market-card<?= $vehicleBrowse ? ' market-card--vehicle' : '' ?><?= $isSold ? ' market-card--sold' : '' ?>">
    <a class="market-card__media" href="/listing.php?id=<?= $lid ?>">
      <?php if ($thumb): ?>
        <?= cx_photo_img($thumb, 'card', ['class' => 'market-card__img', 'alt' => ''], $siteUrl, $uploadsUrl) ?>
      <?php else: ?>
        <div class="market-card__img market-card__img--empty">Fotoğraf yok</div>
      <?php endif; ?>
      <?php if ($isSold): ?>
        <span class="market-card__sold-ribbon">SATILDI</span>
      <?php elseif ($mode === 'SALE'): ?>
        <span class="market-card__badge market-card__badge--sale">SATILIK</span>
      <?php else: ?>
        <span class="market-card__badge market-card__badge--trade">TAKAS</span>
      <?php endif; ?>
      <?php if ($featured && !$isSold): ?>
        <span class="market-card__badge market-card__badge--featured">ÖNE ÇIKAN</span>
      <?php endif; ?>
      <span class="market-card__fav<?= !empty($item['is_favorited']) ? ' is-on' : '' ?>" aria-hidden="true">♥</span>
    </a>
    <?php if ($user): ?>
      <?= $favFormCard ?>
    <?php else: ?>
      <a class="market-card__fav-link" href="<?= cx_e(cx_login_url('/listing.php?id=' . $lid, 'Favori icin giris yapin')) ?>" aria-label="Favorilere ekle">♥</a>
    <?php endif; ?>
    <div class="market-card__body">
      <div class="market-card__price"><?= cx_e(cx_listing_price_line($item)) ?></div>
      <div class="market-card__meta">
        <span><?= cx_e(cx_listing_card_stats_line($item)) ?></span>
        <span><?= cx_e(cx_listing_location_line($item)) ?></span>
      </div>
      <h3 class="market-card__title">
        <a href="/listing.php?id=<?= $lid ?>"><?= cx_e((string) ($item['title'] ?? '')) ?></a>
      </h3>
      <?php if ($vehicleLine !== ''): ?>
      <p class="market-card__vehicle-line"><?= cx_e($vehicleLine) ?></p>
      <?php endif; ?>
      <div class="market-card__actions">
        <a class="market-card__action" href="/listing.php?id=<?= $lid ?>" title="Detay">👁</a>
      </div>
    </div>
  </article>
<?php endforeach; ?>
</div>
