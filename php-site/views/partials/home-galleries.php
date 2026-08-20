<?php

declare(strict_types=1);

/** @var list<array<string,mixed>> $galleryHits */
/** @var array<string,mixed> $app */

$galleryHits = $galleryHits ?? [];
$app = $app ?? cx_app_config();
$uploadsUrl = (string) ($app['uploads_url'] ?? '/uploads');

if ($galleryHits === []) {
    return;
}
?>
<section class="home-galleries" aria-label="Galeriler">
  <div class="home-galleries__head">
    <h2 class="home-galleries__title">Galeriler / Mağazalar</h2>
    <span class="home-galleries__count"><?= count($galleryHits) ?> sonuç</span>
  </div>
  <div class="home-galleries__grid">
    <?php foreach ($galleryHits as $g):
        $gid = (int) ($g['id'] ?? 0);
        $name = (string) ($g['display_name'] ?? $g['username'] ?? 'Galeri');
        $logo = cx_user_avatar_src((string) ($g['avatar_url'] ?? ''), $uploadsUrl);
        $city = trim((string) ($g['city'] ?? ''));
        $isVip = ((string) ($g['role'] ?? '')) === 'vip_kurumsal';
        $verified = cx_gallery_is_verified($g);
        $st = is_array($g['stats'] ?? null) ? $g['stats'] : [];
        $listingN = (int) ($st['listings'] ?? 0);
        $new30 = (int) ($st['new_last_30'] ?? 0);
        $url = (string) ($g['public_url'] ?? ('/galeri.php?id=' . $gid));
    ?>
    <a class="home-gallery-card<?= $isVip ? ' home-gallery-card--vip' : '' ?>" href="<?= cx_e($url) ?>">
      <div class="home-gallery-card__logo<?= $logo === '' ? ' home-gallery-card__logo--mono' : '' ?>">
        <?php if ($logo !== ''): ?>
          <img src="<?= cx_e($logo) ?>" alt="">
        <?php else: ?>
          <span><?= cx_e(mb_strtoupper(mb_substr($name, 0, 1))) ?></span>
        <?php endif; ?>
      </div>
      <div class="home-gallery-card__body">
        <div class="home-gallery-card__top">
          <strong class="home-gallery-card__name"><?= cx_e($name) ?></strong>
          <?php if ($verified): ?><span class="home-gallery-card__badge">✓ Doğrulanmış</span><?php elseif ($isVip): ?><span class="home-gallery-card__badge">VIP</span><?php else: ?><span class="home-gallery-card__badge home-gallery-card__badge--corp">Kurumsal</span><?php endif; ?>
        </div>
        <?php if ($city !== ''): ?>
        <div class="home-gallery-card__meta">📍 <?= cx_e($city) ?></div>
        <?php endif; ?>
        <div class="home-gallery-card__meta"><?= $listingN ?> aktif araç<?php if ($new30 > 0): ?> · <?= $new30 ?> yeni / 30g<?php endif; ?> · Mağazaya git →</div>
      </div>
    </a>
    <?php endforeach; ?>
  </div>
</section>
